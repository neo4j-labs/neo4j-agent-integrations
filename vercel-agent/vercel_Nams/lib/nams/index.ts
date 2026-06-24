/**
 * Neo4j Agent Memory (NAMS) — unified entry point.
 *
 * Two integration modes backed by the same @neo4j-labs/agent-memory client:
 *
 * ┌──────────────┬────────────────────────────────────────────────────────────┐
 * │ Mode         │ What it does                                               │
 * ├──────────────┼────────────────────────────────────────────────────────────┤
 * │ provider     │ Wraps the model via LanguageModelV3Middleware. Memory is   │
 * │              │ retrieved + persisted automatically, no tool calls needed. │
 * │              │
 * ├──────────────┼────────────────────────────────────────────────────────────┤
 * │ tools        │ Exposes query_memory / store_memory as AI SDK tool()s.     │
 * │              │ The model decides when to call them (model-driven).        │
 * │              │ tool-call trace visible in UI.          │
 * └──────────────┴────────────────────────────────────────────────────────────┘
 *
 * Usage — pick the mode that fits:
 *
 * @example Provider mode (transparent, no tools in streamText)
 * ```ts
 * const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const model = nams.wrap(openai('gpt-4o-mini'), { userId });
 * return streamText({ model, messages }).toUIMessageStreamResponse();
 * ```
 *
 * @example Tools mode (model decides when to query/store)
 * ```ts
 * const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const tools = nams.tools({ userId });
 * return streamText({ model: openai('gpt-4o-mini'), tools, messages, stopWhen: stepCountIs(10) })
 *   .toUIMessageStreamResponse();
 * }}
 * ```
 * @example Flag-driven (env var selects mode at runtime)
 * ```ts
 * const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const mode = (process.env.NAMS_MODE ?? 'provider') as NamsMode;
 *
 * if (mode === 'provider') {
 *   const model = nams.wrap(openai('gpt-4o-mini'), { userId });
 *   return streamText({ model, messages }).toUIMessageStreamResponse();
 * } else {
 *   const tools = nams.tools({ userId });
 *   return streamText({ model: openai('gpt-4o-mini'), tools, messages, stopWhen: stepCountIs(10) })
 *     .toUIMessageStreamResponse();
 * }
 * ```
 */

export type { NamsConfig, NamsScope, MemoryHit, StoreInput, GraphExtractor } from './client';
export type { NamsMemoryConfig } from './provider';
export type {
  NamsToolsOptions, QueryInput, StoreInput as ToolStoreInput,
  QueryOutput, StoreOutput
} from './tools';
export type { NamsProviderOptions } from './nams-provider';

export { makeClient, resolveConversation, findExistingConversation, retrieveMemories, storeMemory } from './client';
export { createGraphExtractor } from './extract';
export { createNamsMemory } from './provider';
export { createNamsMemoryTools, NamsMemoryTools } from './tools';
export { createNamsProvider } from './nams-provider';

import type { LanguageModel } from 'ai';
import type { LanguageModelV3 } from '@ai-sdk/provider';
import type { NamsConfig, NamsScope } from './client';
import type { NamsMemoryConfig } from './provider';
import { createNamsMemory } from './provider';
import { createNamsMemoryTools } from './tools';

/** The two NAMS integration modes. */
export type NamsMode = 'provider' | 'tools';

export interface NamsFactoryConfig extends NamsConfig {
  extractionModel?: LanguageModel;
  injectLimit?: number;
  persistInteractions?: boolean;
}


/**
 * Create a unified NAMS instance that supports both integration modes.
 *
 * - `.wrap(model, scope)`  → provider mode (transparent middleware)
 * - `.tools(scope)`        → tools mode (explicit query_memory / store_memory)
 *
 */
export function createNams(config: NamsFactoryConfig) {
  const providerConfig: NamsMemoryConfig = {
    apiKey: config.apiKey,
    endpoint: config.endpoint,
    workspaceId: config.workspaceId,
    extractionModel: config.extractionModel,
    injectLimit: config.injectLimit,
    persistInteractions: config.persistInteractions,
  };

  const memory = createNamsMemory(providerConfig);

  return {
    /**
     * MODE 1 — Provider (transparent).
     * Wrap any LanguageModel; memory is retrieved + persisted automatically.
     * No need to pass memory tools — the middleware owns the full lifecycle.
     */
    wrap(model: LanguageModelV3, scope: NamsScope): LanguageModelV3 {
      return memory.wrap(model, scope);
    },

    /**
     * MODE 2 — Tools (model-driven).
     * Returns `{ query_memory, store_memory }` for use in `streamText({ tools })`.
     * Pair with a system prompt that instructs query → answer → store.
     */
    tools(scope: NamsScope) {
      return createNamsMemoryTools({
        ...config,
        userId: scope.userId,
        conversationId: scope.conversationId,
        extractionModel: config.extractionModel,
      });
    },
  };
}
