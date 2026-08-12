/**
 * Memory mode `hooks` — the recall half.
 *
 * Resolves on `turn.started` (not `session.started`) so a fact stored on turn 1
 * is already in the prompt on turn 2 of the same session. Returns `null` in the
 * other modes, where the model wrapper or the memory tools do the retrieving.
 */
import { defineDynamic, defineInstructions } from "eve/instructions";
import { MAX_MEMORIES, MEMORY_MODE, recall, renderMemories } from "../lib/nams";
import { memoryScope } from "../lib/scope";

export default defineDynamic({
  events: {
    "turn.started": async (event, ctx) => {
      if (MEMORY_MODE !== "hooks") return null;

      // Retrieve against what the user actually just asked, so the injected
      // block is relevant to this turn rather than a generic dump.
      const query = latestUserText(event) ?? "user preferences and research interests";

      try {
        const memories = await recall(memoryScope(ctx), query, MAX_MEMORIES);
        if (memories.length === 0) return null;
        return defineInstructions({ markdown: renderMemories(memories) });
      } catch (error) {
        // Memory is an enhancement, never a hard dependency: a NAMS outage
        // should degrade the answer, not fail the turn.
        console.warn("[nams] recall failed, continuing without memory", error);
        return null;
      }
    },
  },
});

/** Best-effort read of the message that started this turn. */
function latestUserText(event: unknown): string | undefined {
  const message = (event as { data?: { message?: unknown } })?.data?.message;
  if (typeof message === "string" && message.trim()) return message.trim().slice(0, 500);
  return undefined;
}
