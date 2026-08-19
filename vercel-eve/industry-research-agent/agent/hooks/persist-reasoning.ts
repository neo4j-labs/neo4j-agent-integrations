/**
 * Reasoning memory — the agent's own decision trail.
 *
 * NAMS has three memory types. Short-term (the conversation) and long-term
 * (entities and preferences) are written by `./persist-turn.ts`. The third,
 * reasoning, records *why* the agent answered as it did: one step per reasoning
 * block, with the tool calls that step invoked hanging off it. Nothing else
 * writes it, so this hook never double-stores a turn — see `REASONING_ENABLED`
 * in `../lib/nams`.
 *
 * That trail is what makes "why did you recommend that?" answerable from
 * recorded provenance instead of from a plausible-sounding reconstruction.
 *
 * Why everything is buffered and flushed on `turn.completed` rather than
 * written as each event arrives: a step's tool calls are only known *after*
 * its `reasoning.completed` fires, and `recordToolCall` needs the id of the
 * step it belongs to. Buffering also keeps the write off the streaming path,
 * so recording provenance never delays the answer.
 */
import { defineState } from "eve/context";
import { defineHook } from "eve/hooks";
import { memory } from "../lib/memory-gateway";
import {
  REASONING_ENABLED,
  serializeToolResult,
  type ReasoningStepInput,
  type ReasoningToolCall,
} from "../lib/nams";
import { memoryScope } from "../lib/scope";

/** Durable state is JSON, so step indices are string keys here. */
interface PendingTrace {
  /** stepIndex → the reasoning block that step emitted. */
  readonly blocks: Record<string, string>;
  /** callId → the arguments the model requested, kept until the result lands. */
  readonly requested: Record<string, { toolName: string; args: Record<string, unknown> }>;
  /** stepIndex → the tool calls that completed during that step. */
  readonly calls: Record<string, ReasoningToolCall[]>;
}

const EMPTY: PendingTrace = { blocks: {}, requested: {}, calls: {} };

const pendingTrace = defineState<PendingTrace>("nams.pending-trace", () => EMPTY);

export default defineHook({
  events: {
    // Arguments arrive with the request and are gone by the time the result
    // does, so hold them by callId until the matching result shows up.
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
          // Serialize at capture time so the buffered turn state stays small too.
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
      // A step can emit several reasoning blocks; keep them in order.
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
        // A hook that throws fails the turn. Provenance is an enhancement, so
        // losing it must never cost the user an answer they already have.
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

    // A step with neither is a bare model reply; there is no provenance in it.
    if (!reasoning && toolCalls.length === 0) continue;

    steps.push({
      // Low-effort reasoning models often call tools without emitting a block.
      // The tool calls are still provenance worth keeping, so record the step
      // and say plainly that the rationale was not exposed.
      reasoning: reasoning ?? "(model emitted no reasoning block for this step)",
      actionTaken: toolCalls.length > 0 ? toolCalls.map((c) => c.toolName).join(", ") : "respond",
      result: toolCalls.length > 0 ? `${toolCalls.length} tool call(s)` : undefined,
      toolCalls,
    });
  }
  return steps;
}
