// Saves each question and answer to NAMS when the turn ends.
import { defineState } from "eve/context";
import { defineHook } from "eve/hooks";
import { memory } from "../lib/memory-gateway";
import { GRAPH_MEMORY_ENABLED, memoryScope } from "../lib/nams";

interface PendingTurn {
  readonly user: string | null;
  readonly assistant: string | null;
}

const pendingTurn = defineState<PendingTurn>("nams.pending-turn", () => ({
  user: null,
  assistant: null,
}));

export default defineHook({
  events: {
    "message.received"(event) {
      const user = event.data.message?.trim();
      if (user) pendingTurn.update((s) => ({ ...s, user }));
    },

    // Keep the last assistant message with text.
    "message.completed"(event) {
      const assistant = event.data.message?.trim();
      if (assistant) pendingTurn.update((s) => ({ ...s, assistant }));
    },

    async "turn.completed"(_event, ctx) {
      const { user, assistant } = pendingTurn.get();
      pendingTurn.update(() => ({ user: null, assistant: null }));
      if (!user) return;

      const content = assistant
        ? `User asked: ${truncate(user)}\nAgent answered: ${truncate(assistant)}`
        : `User asked: ${truncate(user)}`;

      const userMemory = memory.for(memoryScope(ctx));

      // Save to the chat log. Only log errors: a hook that throws breaks the turn.
      try {
        await userMemory.remember({ content, type: "interaction" });
      } catch (error) {
        console.warn("[nams] failed to persist turn", error);
      }

      // Also save to the long-term graph. Separate call, so a failure here keeps the chat log.
      if (!GRAPH_MEMORY_ENABLED || !assistant || !isPromotable(user)) return;

      try {
        await userMemory.remember({ content, type: "fact" });
      } catch (error) {
        console.warn("[nams] failed to promote turn to the entity graph", error);
      }
    },
  },
});

function truncate(text: string, max = 1200): string {
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}

/** Skip slash commands: they control eve and aren't facts worth keeping. */
function isPromotable(user: string): boolean {
  return !user.startsWith("/");
}
