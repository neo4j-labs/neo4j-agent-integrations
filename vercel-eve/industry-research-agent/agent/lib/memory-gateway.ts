/**
 * The MemoryGateway — the agent's only door to NAMS.
 *
 * Every SDK call in this project happens in this file. Hooks, tools, dynamic
 * instructions, and `agent.ts` all go through `memory.for(scope)` and never
 * import `@neo4j-labs/nams-ai-provider` themselves. That is the whole point of
 * a gateway: memory is a capability the agent depends on, not a library it is
 * built out of, so retries, timeouts, tracing, a workspace policy, or a
 * different backend entirely are all one-file changes.
 *
 * The unit of memory is a **user**, so the gateway hands out one
 * `MemoryClient` per user id and reuses it:
 *
 *   1. `resolveConversation` caches the user's conversation id in state keyed
 *      by the client *instance* (a WeakMap inside the provider). Build a fresh
 *      client per call — the obvious thing to do — and that cache is always
 *      cold, so every recall and every store pays an extra `list_conversations`
 *      round trip before it does any work.
 *   2. `workspaceId` is fixed when the client is constructed. One NAMS
 *      workspace per tenant is the only hard isolation NAMS offers today
 *      (long-term entities carry no user id — see README, "Challenges"), and
 *      that policy is only expressible if each tenant has its own client.
 *
 * The map key *is* the namespace. Nothing in this file reads a user id from
 * anywhere but the `NamsScope` it was handed, and `memoryScope` in
 * `agent/lib/nams.ts` derives that scope from verified session auth only.
 */
import {
  findExistingConversation,
  makeClient,
  resolveConversation,
  retrieveMemories,
  storeMemory,
} from "@neo4j-labs/nams-ai-provider";
import type { GraphExtractor } from "@neo4j-labs/nams-ai-provider";
import type { MemoryClient } from "@neo4j-labs/agent-memory";
import { createGraphExtractor } from "./graph-extractor";
import { extractionModel } from "./model";
import {
  GRAPH_MEMORY_ENABLED,
  MAX_MEMORIES,
  namsConfig,
  workspaceIdFor,
  type MemoryHit,
  type NamsConfig,
  type NamsScope,
  type ReasoningStepInput,
  type StoreMemoryInput,
} from "./nams";

/**
 * The entity extractor, shared by every user.
 *
 * Without one, `storeMemory` falls back to a single flat node whose name is the
 * first words of the memory — a sentence-shaped entity per turn, which is worse
 * than no graph at all. With one, a stored memory becomes real entities and the
 * relationships between them.
 *
 * The extractor is `./graph-extractor`, not the provider's — see that file for
 * the prompt and the entity filter that differ.
 *
 * Built once and lazily: `extractionModel()` reads credentials from the
 * environment, so constructing it at module load would make an unrelated import
 * of this file throw on a machine with no model credential. A failure is
 * remembered, not retried — a missing credential does not become one failed
 * model call per turn for the life of the instance.
 */
let extractor: GraphExtractor | undefined;
let extractorUnavailable = false;

function graphExtractor(): GraphExtractor | undefined {
  if (!GRAPH_MEMORY_ENABLED || extractorUnavailable) return undefined;
  if (!extractor) {
    try {
      extractor = createGraphExtractor(extractionModel());
    } catch (error) {
      extractorUnavailable = true;
      console.warn("[nams] no extraction model — long-term memory falls back to flat entities", error);
      return undefined;
    }
  }
  return extractor;
}

/**
 * How many per-user clients to keep. A warm serverless instance can serve many
 * users over its life, and each client holds a conversation-id cache, so the
 * map is bounded and evicts least-recently-used.
 */
const MAX_CACHED_USERS = Number(process.env.NAMS_CLIENT_CACHE ?? 256);

/** Everything the agent is allowed to do with one user's memory. */
interface UserMemory {
  readonly userId: string;

  /** Search all four NAMS sources (long-term, conversation, cross-session, reasoning). */
  recall(query: string, limit?: number): Promise<MemoryHit[]>;

  /** Persist one memory. `interaction` goes to short-term; the rest build the long-term graph. */
  remember(input: StoreMemoryInput): Promise<void>;

  /** Persist a turn's reasoning steps and the tool calls each one made. */
  rememberReasoning(steps: readonly ReasoningStepInput[]): Promise<void>;
}

interface UserEntry {
  readonly config: NamsConfig;
  readonly client: MemoryClient;
}

class MemoryGateway {
  /** userId → that user's client. Insertion order is the LRU order. */
  readonly #users = new Map<string, UserEntry>();

  /** The per-user handle. Cheap: everything expensive is cached on the entry. */
  for(scope: NamsScope): UserMemory {
    const userId = scope.userId;
    if (!userId) throw new Error("MemoryGateway.for() requires a userId — see memoryScope in agent/lib/nams.ts");

    const entry = this.#entry(userId);
    // Conversation stays unpinned unless the caller pinned one: NAMS then
    // reuses the user's most recent conversation, which is what makes recall
    // work across eve sessions.
    const userScope: NamsScope = { userId, conversationId: scope.conversationId };

    return {
      userId,

      recall: async (query, limit = MAX_MEMORIES) => {
        const conversationId = await resolveConversation(entry.client, entry.config, userScope);
        return retrieveMemories(entry.client, userScope, conversationId, query, limit);
      },

      remember: async (input) => {
        const conversationId = await resolveConversation(entry.client, entry.config, userScope);
        // Ignored for `interaction`, which never reaches the long-term half of
        // `storeMemory`; load-bearing for every other type.
        await storeMemory(entry.client, conversationId, input, { extractor: graphExtractor() });
      },

      rememberReasoning: async (steps) => {
        if (steps.length === 0) return;

        // `findExistingConversation`, not `resolveConversation`: a trace is
        // provenance for a conversation that already happened, so it must never
        // be the thing that creates one. No conversation yet means the turn
        // stored nothing to hang a trace off, and we skip.
        const conversationId = await findExistingConversation(entry.client, entry.config, userScope);
        if (!conversationId) return;

        for (const step of steps) {
          const recorded = await entry.client.reasoning.recordStep({
            conversationId,
            reasoning: step.reasoning,
            actionTaken: step.actionTaken,
            result: step.result,
          });

          for (const call of step.toolCalls ?? []) {
            await entry.client.reasoning.recordToolCall(recorded.id, call.toolName, call.arguments, {
              result: call.result,
              status: call.failed ? "failure" : "success",
            });
          }
        }
      },
    };
  }

  #entry(userId: string): UserEntry {
    const cached = this.#users.get(userId);
    if (cached) {
      // Refresh LRU position.
      this.#users.delete(userId);
      this.#users.set(userId, cached);
      return cached;
    }

    const config: NamsConfig = { ...namsConfig(), workspaceId: workspaceIdFor(userId) };
    const entry: UserEntry = { config, client: makeClient(config) };

    this.#users.set(userId, entry);
    if (this.#users.size > MAX_CACHED_USERS) {
      const oldest = this.#users.keys().next().value;
      if (oldest !== undefined) this.#users.delete(oldest);
    }
    return entry;
  }
}

/**
 * The gateway instance. Module scope, so it lives as long as the serverless
 * instance does and its caches survive between turns of the same session.
 */
export const memory = new MemoryGateway();
