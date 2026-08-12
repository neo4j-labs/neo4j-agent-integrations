/**
 * Memory mode `hooks` — the retention half.
 *
 * Storage is deterministic: the runtime tells us a turn happened, so nothing
 * depends on the model choosing to call a save tool. The exchange is buffered
 * across the turn in durable session state and written once on `turn.completed`.
 *
 * Inactive unless `NAMS_MODE=hooks`; in the other modes the model wrapper or
 * the `remember` tool owns persistence.
 */
import { defineState } from "eve/context";
import { defineHook } from "eve/hooks";
import { MEMORY_MODE, remember } from "../lib/nams";
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
      if (MEMORY_MODE !== "hooks") return;
      const user = event.data.message?.trim();
      if (user) pendingTurn.update((s) => ({ ...s, user }));
    },

    // A turn can complete several assistant messages (a reply, then a tool
    // call, then a reply). Keep the last one with text.
    "message.completed"(event) {
      if (MEMORY_MODE !== "hooks") return;
      const assistant = event.data.message?.trim();
      if (assistant) pendingTurn.update((s) => ({ ...s, assistant }));
    },

    async "turn.completed"(_event, ctx) {
      if (MEMORY_MODE !== "hooks") return;

      const { user, assistant } = pendingTurn.get();
      pendingTurn.update(() => ({ user: null, assistant: null }));
      if (!user) return;

      const content = assistant
        ? `User asked: ${truncate(user)}\nAgent answered: ${truncate(assistant)}`
        : `User asked: ${truncate(user)}`;

      try {
        await remember(memoryScope(ctx), { content, type: "interaction" });
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
