/**
 * Reasoning memory — the agent's own decision trail.
 */
import { defineState } from "eve/context";
import { defineHook } from "eve/hooks";
import { memory } from "../lib/memory-gateway";
import {
  REASONING_ENABLED,
  memoryScope,
  serializeToolResult,
  type ReasoningStepInput,
  type ReasoningToolCall,
} from "../lib/nams";

interface PendingTrace {
  readonly blocks: Record<string, string>;
  readonly requested: Record<string, { toolName: string; args: Record<string, unknown> }>;
  readonly calls: Record<string, ReasoningToolCall[]>;
}

const EMPTY: PendingTrace = { blocks: {}, requested: {}, calls: {} };

const pendingTrace = defineState<PendingTrace>("nams.pending-trace", () => EMPTY);

export default defineHook({
  events: {
    "actions.requested"(event) {
      if (!REASONING_ENABLED) return;

      const requested: Record<string, { toolName: string; args: Record<string, unknown> }> = {};
      for (const action of event.data.actions) {
        if (action.kind !== "tool-call") continue;
        requested[action.callId] = { toolName: action.toolName, args: action.input };
      }
      if (Object.keys(requested).length === 0) return;

      pendingTrace.update((s) => ({ ...s, requested: { ...s.requested, ...requested } }));
    },

    "action.result"(event) {
      if (!REASONING_ENABLED) return;

      const { result } = event.data;
      if (result.kind !== "tool-result") return;

      const key = String(event.data.stepIndex);

      pendingTrace.update((s) => {
        const { [result.callId]: pending, ...requested } = s.requested;
        const call: ReasoningToolCall = {
          toolName: result.toolName,
          arguments: pending?.args ?? {},
          result: serializeToolResult(result.output),
          failed: result.isError === true,
        };
        return {
          ...s,
          requested,
          calls: { ...s.calls, [key]: [...(s.calls[key] ?? []), call] },
        };
      });
    },

    "reasoning.completed"(event) {
      if (!REASONING_ENABLED) return;

      const reasoning = event.data.reasoning?.trim();
      if (!reasoning) return;

      const key = String(event.data.stepIndex);
      pendingTrace.update((s) => ({
        ...s,
        blocks: { ...s.blocks, [key]: s.blocks[key] ? `${s.blocks[key]}\n\n${reasoning}` : reasoning },
      }));
    },

    async "turn.completed"(_event, ctx) {
      if (!REASONING_ENABLED) return;

      const { blocks, calls } = pendingTrace.get();
      pendingTrace.update(() => EMPTY);

      const steps = buildSteps(blocks, calls);
      if (steps.length === 0) return;

      try {
        await memory.for(memoryScope(ctx)).rememberReasoning(steps);
      } catch (error) {
        console.warn("[nams] failed to persist reasoning trace", error);
      }
    },
  },
});

/** Pair each step's reasoning with its tool calls, oldest step first. */
function buildSteps(
  blocks: Record<string, string>,
  calls: Record<string, ReasoningToolCall[]>,
): ReasoningStepInput[] {
  const indices = [...new Set([...Object.keys(blocks), ...Object.keys(calls)])].sort(
    (a, b) => Number(a) - Number(b),
  );

  const steps: ReasoningStepInput[] = [];
  for (const index of indices) {
    const reasoning = blocks[index];
    const toolCalls = calls[index] ?? [];

    if (!reasoning && toolCalls.length === 0) continue;

    steps.push({
      reasoning: reasoning ?? "(model emitted no reasoning block for this step)",
      actionTaken: toolCalls.length > 0 ? toolCalls.map((c) => c.toolName).join(", ") : "respond",
      result: toolCalls.length > 0 ? `${toolCalls.length} tool call(s)` : undefined,
      toolCalls,
    });
  }
  return steps;
}
