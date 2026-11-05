// Records each turn's reasoning steps and tool calls in NAMS, on the conversation
// the namsMemory() provider saves the turn to. That provider only saves messages,
// so without this the conversation's reasoning trace stays empty.
import type { ModelMessage } from "ai";
import type { MemoryClient } from "@neo4j-labs/agent-memory";
import { makeClient } from "@neo4j-labs/nams-ai-provider";
import {
  defineMemoryProvider,
  type MemoryProvider,
  type MemoryTurnCompletedContext,
} from "eve/memory";

export interface ReasoningTraceOptions {
  apiKey?: string;
  endpoint?: string;
  workspaceId?: string;
  enabled?: boolean;
}

interface ToolCallRecord {
  toolName: string;
  args: Record<string, unknown>;
  result?: string;
  failed: boolean;
}

interface StepRecord {
  reasoning: string;
  actionTaken: string;
  result?: string;
  toolCalls: ToolCallRecord[];
}

const LIMITS = { reasoning: 2000, result: 500, toolResult: 2000, listed: 200, memo: 500 };

/** Wraps a NAMS eve provider so each captured turn also records its reasoning trace. */
export function withReasoningTrace(provider: MemoryProvider, options: ReasoningTraceOptions = {}): MemoryProvider {
  if (options.enabled === false) return provider;

  const conversations = new Map<string, string>();
  const recorded = new Set<string>();
  let client: MemoryClient | undefined;

  const getClient = (): MemoryClient => {
    const apiKey = options.apiKey ?? process.env.MEMORY_API_KEY;
    if (!apiKey) throw new Error("withReasoningTrace(): no NAMS API key");
    client ??= makeClient({ apiKey, endpoint: options.endpoint, workspaceId: options.workspaceId });
    return client;
  };

  /** The session conversation namsMemory() created for this eve session (same metadata it writes). */
  async function sessionConversation(nams: MemoryClient, ctx: MemoryTurnCompletedContext): Promise<string | undefined> {
    const userId = ctx.memory.scope.key;
    const key = JSON.stringify([userId, ctx.memory.slot, ctx.session.id]);
    const known = conversations.get(key);
    if (known) return known;

    const listed = await nams.shortTerm.listConversations({ userId, limit: LIMITS.listed });
    const found = listed.find((c) =>
      c.userId === userId &&
      c.metadata?.source === "eve" &&
      c.metadata?.kind === "session" &&
      c.metadata?.slot === ctx.memory.slot &&
      c.metadata?.session === ctx.session.id)?.id;
    if (found) remember(conversations, key, found);
    return found;
  }

  async function record(ctx: MemoryTurnCompletedContext): Promise<void> {
    if (recorded.has(ctx.operationId)) return;
    const steps = turnSteps(ctx.messages);
    if (steps.length === 0) return;

    const nams = getClient();
    const conversationId = await sessionConversation(nams, ctx);
    if (!conversationId) {
      console.warn("[nams] no session conversation found; reasoning trace not saved");
      return;
    }

    for (const step of steps) {
      const saved = await nams.reasoning.recordStep({
        conversationId,
        reasoning: step.reasoning,
        actionTaken: step.actionTaken,
        result: step.result,
      });
      for (const call of step.toolCalls) {
        // NAMS stores "" for a non-string result, so results are always serialized first.
        await nams.reasoning.recordToolCall(saved.id, call.toolName, call.args, {
          result: call.result,
          status: call.failed ? "failure" : "success",
        });
      }
    }
    remember(recorded, ctx.operationId);
  }

  const capture = provider.capture?.["turn.completed"];

  return defineMemoryProvider({
    recall: provider.recall,
    capture: {
      ...(provider.capture?.["compaction.requested"]
        ? { "compaction.requested": provider.capture["compaction.requested"] }
        : {}),
      async "turn.completed"(ctx) {
        // The provider's capture runs first: it creates the conversation the trace hangs off.
        await capture?.(ctx);
        try {
          await record(ctx);
        } catch (error) {
          if (ctx.abortSignal.aborted) throw error;
          console.warn("[nams] failed to save reasoning trace", error);
        }
      },
    },
    ...(provider.tools ? { tools: provider.tools } : {}),
  });
}

/**
 * One step per model call in the turn, oldest first: its reasoning (or narration),
 * the tools it called, and what they returned. The turn is everything after the
 * last user message; each assistant message there is one model call.
 */
export function turnSteps(messages: readonly ModelMessage[]): StepRecord[] {
  let start = messages.length;
  while (start > 0 && messages[start - 1].role !== "user") start--;
  const turn = messages.slice(start);

  const results = new Map<string, { output: unknown; failed: boolean }>();
  for (const message of turn) {
    if (message.role !== "tool") continue;
    for (const part of message.content) {
      if (part.type !== "tool-result") continue;
      const output = part.output as { type: string; value?: unknown };
      results.set(part.toolCallId, {
        output: output.value ?? output,
        failed: output.type === "error-text" || output.type === "error-json" || output.type === "execution-denied",
      });
    }
  }

  const steps: StepRecord[] = [];
  for (const message of turn) {
    if (message.role !== "assistant") continue;
    const parts = typeof message.content === "string"
      ? [{ type: "text" as const, text: message.content }]
      : message.content;

    const reasoning = joinText(parts, "reasoning");
    const text = joinText(parts, "text");
    const toolCalls: ToolCallRecord[] = parts.flatMap((part) => {
      if (part.type !== "tool-call") return [];
      const result = results.get(part.toolCallId);
      return [{
        toolName: part.toolName,
        args: isRecord(part.input) ? part.input : { input: part.input },
        result: serialize(result?.output, LIMITS.toolResult),
        failed: result?.failed ?? false,
      }];
    });
    if (!reasoning && !text && toolCalls.length === 0) continue;

    const toolNames = toolCalls.map((c) => c.toolName).join(", ");
    steps.push({
      reasoning: cap(
        reasoning || text || `Step ${steps.length + 1}${toolNames ? ` — ${toolNames}` : ""}`,
        LIMITS.reasoning,
      ),
      // "direct response" is the action nams-ai-provider reads back as a reasoning memory.
      actionTaken: toolNames || "direct response",
      result: toolCalls.length > 0
        ? cap(toolCalls.map((c) => `${c.toolName}: ${c.failed ? "failed" : c.result ?? "(no output)"}`).join("; "), LIMITS.result)
        : text ? cap(text, LIMITS.result) : undefined,
      toolCalls,
    });
  }
  return steps;
}

function joinText(parts: ReadonlyArray<{ type: string; text?: unknown }>, type: "text" | "reasoning"): string {
  return parts
    .filter((p) => p.type === type && typeof p.text === "string")
    .map((p) => p.text as string)
    .join("\n\n")
    .trim();
}

function serialize(value: unknown, max: number): string | undefined {
  if (value === undefined) return undefined;
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text === undefined ? undefined : cap(text, max);
}

function cap(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Adds to a memo, evicting the oldest entry past LIMITS.memo. */
function remember<K>(memo: Map<K, string> | Set<K>, key: K, value?: string): void {
  if (memo instanceof Map) memo.set(key, value as string);
  else memo.add(key);
  if (memo.size > LIMITS.memo) memo.delete(memo.keys().next().value as K);
}
