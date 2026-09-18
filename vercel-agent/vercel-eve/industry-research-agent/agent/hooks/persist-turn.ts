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

      const userMemory = memory.for(memoryScope(ctx));

      // Short-term: the conversation thread. Always written, so the transcript
      // survives even when promotion is off or the extractor fails.
      try {
        await userMemory.remember({ content, type: "interaction" });
      } catch (error) {
        // A hook that throws fails the turn. Memory is an enhancement, so
        // swallow the failure and keep the answer the user already received.
        console.warn("[nams] failed to persist turn", error);
      }

      // Long-term: the entity graph. A separate write with a separate catch —
      // `storeMemory` returns early on `interaction` and never touches
      // `longTerm`, so this second call is the only thing in the project that
      // moves the graph. Its failure must not cost us the transcript above.
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

/**
 * Whether a turn is worth promoting into the entity graph.
 *
 * Slash commands are addressed to the runtime, not to the domain, and
 * extracting them pollutes the graph with the agent's own vocabulary:
 * `/channels` is what put `analysis`, `final`, `private reasoning` and
 * `concise wrap-up` into the workspace as `Concept` entities. Extraction costs
 * a model call and an entity is awkward to unmake — NAMS has no delete — so the
 * filter is cheap and runs first.
 */
function isPromotable(user: string): boolean {
  return !user.startsWith("/");
}
