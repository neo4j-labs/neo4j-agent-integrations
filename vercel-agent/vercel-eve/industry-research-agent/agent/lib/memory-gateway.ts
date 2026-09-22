// The only file that talks to the NAMS SDK. Keeps one client per user, so each
// user's conversation is reused and can have its own workspace.
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

// Created on first use (it needs model credentials). If that fails, don't retry.
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

/** Max users to cache. The least recently used is dropped first. */
const MAX_CACHED_USERS = Number(process.env.NAMS_CLIENT_CACHE ?? 250);

/** Everything the agent is allowed to do with one user's memory. */
interface UserMemory {
  readonly userId: string;

  /** Search every kind of memory: long-term, conversation, cross-session, reasoning. */
  recall(query: string, limit?: number): Promise<MemoryHit[]>;

  /** Save one memory. */
  remember(input: StoreMemoryInput): Promise<void>;

  /** Save a turn's reasoning steps and their tool calls. */
  rememberReasoning(steps: readonly ReasoningStepInput[]): Promise<void>;
}

interface UserEntry {
  readonly config: NamsConfig;
  readonly client: MemoryClient;
}

class MemoryGateway {
  /** One client per user, least recently used first. */
  readonly #users = new Map<string, UserEntry>();

  for(scope: NamsScope): UserMemory {
    const userId = scope.userId;
    if (!userId) throw new Error("MemoryGateway.for() requires a userId — see memoryScope in agent/lib/nams.ts");

    const entry = this.#entry(userId);
    const userScope: NamsScope = { userId, conversationId: scope.conversationId };

    return {
      userId,

      recall: async (query, limit = MAX_MEMORIES) => {
        const conversationId = await resolveConversation(entry.client, entry.config, userScope);
        return retrieveMemories(entry.client, userScope, conversationId, query, limit);
      },

      remember: async (input) => {
        const conversationId = await resolveConversation(entry.client, entry.config, userScope);
        await storeMemory(entry.client, conversationId, input, { extractor: graphExtractor() });
      },

      rememberReasoning: async (steps) => {
        if (steps.length === 0) return;
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

export const memory = new MemoryGateway();
