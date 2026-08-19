/**
 * Retention — the write half of memory.
 *
 * Storage is deterministic: the runtime tells us a turn happened, so nothing
 * depends on the model choosing to call a save tool. The exchange is buffered
 * across the turn in durable session state — the two halves arrive in different
 * events, which means different steps, and a step can resume on another machine
 * — and written once on `turn.completed`.
 */
import { defineState } from "eve/context";
import { defineHook } from "eve/hooks";
import { memory } from "../lib/memory-gateway";
import { memoryScope } from "../lib/scope";

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

    // A turn can complete several assistant messages (a reply, then a tool
    // call, then a reply). Keep the last one with text.
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

      try {
        await memory.for(memoryScope(ctx)).remember({ content, type: "interaction" });
      } catch (error) {
        // A hook that throws fails the turn. Memory is an enhancement, so
        // swallow the failure and keep the answer the user already received.
        console.warn("[nams] failed to persist turn", error);
      }
    },
  },
});

function truncate(text: string, max = 1200): string {
  return text.length <= max ? text : `${text.slice(0, max)}…`;
}
