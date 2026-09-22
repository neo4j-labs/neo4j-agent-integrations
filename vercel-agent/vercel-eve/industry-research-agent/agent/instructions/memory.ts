// Each turn, search memory with the user's own words (NAMS matches keywords).
import { defineDynamic, defineInstructions } from "eve/instructions";
import { memory } from "../lib/memory-gateway";
import { MAX_MEMORIES, memoryScope, renderMemories } from "../lib/nams";

export default defineDynamic({
  events: {
    "turn.started": async (event, ctx) => {
      const query = latestUserText(event) ?? "user preferences and research interests";

      try {
        const memories = await memory.for(memoryScope(ctx)).recall(query, MAX_MEMORIES);
        if (memories.length === 0) return null;
        return defineInstructions({ markdown: renderMemories(memories) });
      } catch (error) {
        console.warn("[nams] recall failed, continuing without memory", error);
        return null;
      }
    },
  },
});

/** The user's message for this turn, if there is one. */
function latestUserText(event: unknown): string | undefined {
  const message = (event as { data?: { message?: unknown } })?.data?.message;
  if (typeof message === "string" && message.trim()) return message.trim().slice(0, 500);
  return undefined;
}
