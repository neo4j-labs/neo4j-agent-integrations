/**
 * Neo4j Agent Memory (NAMS) — unified entry point.
 *
 * Three integration modes backed by the same @neo4j-labs/agent-memory client:
 *
 * ┌─────────────────┬──────────────────────────────────────────────────────────┐
 * │ Mode            │ What it does                                             │
 * ├─────────────────┼──────────────────────────────────────────────────────────┤
 * │ provider        │ Wraps the model via LanguageModelV3Middleware. Memory is │
 * │ .wrap()         │ retrieved + persisted automatically, no tools needed.    │
 * ├─────────────────┼──────────────────────────────────────────────────────────┤
 * │ tools           │ Exposes query_memory / store_memory as AI SDK tool()s.   │
 * │ .tools()        │ The model decides when to call them (model-driven).      │
 * ├─────────────────┼──────────────────────────────────────────────────────────┤
 * │ tools + MCP     │ Same as tools mode but also connects to an MCP server    │
 * │ .toolsWithMcp() │ and merges its tools. Returns a close() handle.         │
 * └─────────────────┴──────────────────────────────────────────────────────────┘
 *
 * Usage — pick the mode that fits:
 *
 * @example Provider mode (transparent middleware)
 * ```ts
 * const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const model = nams.wrap(openai('gpt-5.4-mini'), { userId });
 * const agent = new ToolLoopAgent({ model, stopWhen: stepCountIs(1) });
 * ```
 *
 * @example Tools mode (model decides when to query/store)
 * ```ts
 * const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const tools = nams.tools({ userId });
 * const agent = new ToolLoopAgent({ model: openai('gpt-5.4-mini'), tools, stopWhen: stepCountIs(10) });
 * ```
 *
 * @example Tools + MCP mode (NAMS memory tools merged with MCP tools)
 * ```ts
 * const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const { tools, close } = await nams.toolsWithMcp(
 *   { userId },
 *   { url: 'http://localhost:3001/mcp', headers: { Authorization: 'Basic ...' } },
 * );
 * const agent = new ToolLoopAgent({ model: openai('gpt-5.4-mini'), tools, stopWhen: stepCountIs(10) });
 * // in onFinish: await close()
 * ```
 *
 * @example Flag-driven (env var selects mode at runtime)
 * ```ts
 * const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
 * const mode = (process.env.NAMS_MODE ?? 'provider') as NamsMode;
 *
 * if (mode === 'provider') {
 *   const model = nams.wrap(openai('gpt-5.4-mini'), { userId });
 *   const agent = new ToolLoopAgent({ model, stopWhen: stepCountIs(1) });
 * } else {
 *   const { tools, close } = await nams.toolsWithMcp({ userId }, mcpConfig);
 *   const agent = new ToolLoopAgent({ model: openai('gpt-5.4-mini'), tools, stopWhen: stepCountIs(10) });
 *   // in onFinish: await close()
 * }
 * ```
 */

export type { NamsConfig, NamsScope, MemoryHit, StoreInput, GraphExtractor } from './client';
export type { NamsMemoryConfig } from './provider';
export type {
  NamsToolsOptions, NamsToolsWithMcpOptions, NamsToolsResult,
  McpConfig, QueryInput, StoreInput as ToolStoreInput,
  QueryOutput, StoreOutput
} from './tools';
export type { NamsProviderOptions } from './nams-provider';

export { makeClient, resolveConversation, findExistingConversation, retrieveMemories, storeMemory } from './client';
export { createGraphExtractor } from './extract';
export { createNamsMemory } from './provider';
export { createNamsMemoryTools, createNamsTools, NamsMemoryTools } from './tools';
export { createNamsProvider } from './nams-provider';

import type { LanguageModel } from 'ai';
import type { LanguageModelV3 } from '@ai-sdk/provider';
import type { NamsConfig, NamsScope } from './client';
import type { NamsMemoryConfig } from './provider';
import type { McpConfig } from './tools';
import { createNamsMemory } from './provider';
import { createNamsMemoryTools, createNamsTools } from './tools';

/** The two NAMS integration modes. */
export type NamsMode = 'provider' | 'tools';

export interface NamsFactoryConfig extends NamsConfig {
  extractionModel?: LanguageModel;
  injectLimit?: number;
  persistInteractions?: boolean;
}

/**
 * Create a unified NAMS instance that supports all three integration modes.
 *
 * - `.wrap(model, scope)`            → provider mode (transparent middleware)
 * - `.tools(scope)`                  → tools mode (query_memory / store_memory)
 * - `.toolsWithMcp(scope, mcpConfig)` → tools + MCP mode (merged tool set)
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
     * MODE 1 — Provider (transparent middleware).
     * Wrap any LanguageModel; memory is retrieved + persisted automatically.
     * No tool calls emitted — pass the returned model directly to ToolLoopAgent.
     */
    wrap(model: LanguageModelV3, scope: NamsScope): LanguageModelV3 {
      return memory.wrap(model, scope);
    },

    /**
     * MODE 2 — Tools (model-driven).
     * Returns { query_memory, store_memory } as AI SDK tool()s.
     * Pair with a system prompt that instructs: query → answer → store.
     */
    tools(scope: NamsScope) {
      return createNamsMemoryTools({
        ...config,
        userId: scope.userId,
        conversationId: scope.conversationId,
        extractionModel: config.extractionModel,
      });
    },

    /**
     * MODE 3 — Tools + MCP (model-driven, extended).
     * Connects to an MCP server and merges its tools with NAMS memory tools.
     * Returns { tools, close } — call close() in ToolLoopAgent's onFinish.
     * When mcpConfig is omitted, behaves identically to .tools() with a no-op close.
     */
    async toolsWithMcp(scope: NamsScope, mcpConfig?: McpConfig) {
      return createNamsTools({
        ...config,
        userId: scope.userId,
        conversationId: scope.conversationId,
        extractionModel: config.extractionModel,
        mcp: mcpConfig,
      });
    },
  };
}
