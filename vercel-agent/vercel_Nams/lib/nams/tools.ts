/**
 * Mode 2 — Custom Tools (model-driven)
 *
 * createNamsMemoryTools(options) returns { query_memory, store_memory } —
 * two AI SDK tool() objects the model can call when it decides memory matters.
 *
 * Pass them to streamText's `tools:` field. Pair with a system prompt that
 * instructs the model to query first, answer, then store (see SYSTEM_PROMPT
 * in lib/constants.ts for a complete example).
 *
 * @example
 * const tools = createNamsMemoryTools({ apiKey, userId, conversationId });
 * return streamText({ model, system, messages, tools, stopWhen: stepCountIs(10) })
 *   .toUIMessageStreamResponse();
 */

import { tool, zodSchema, type LanguageModel } from 'ai';
import { z } from 'zod';
import {
  makeClient,
  resolveConversation,
  retrieveMemories,
  storeMemory,
  type NamsConfig,
  type NamsScope,
  type MemoryHit,
} from './client';
import { createGraphExtractor } from './extract';

// ─── Schemas ──────────────────────────────────────────────────────────────────

const querySchema = z.object({
  query: z.string().describe('Keywords or phrase to search in memory'),
  limit: z.number().int().min(1).max(20).default(5),
});

const storeSchema = z.object({
  content: z.string().min(1).max(2000).describe('The information to remember'),
  type: z.enum(['fact', 'interaction', 'pattern', 'user_preference']).describe(
    'fact=persistent knowledge | interaction=conversation event | ' +
    'pattern=recurring behaviour | user_preference=explicit setting',
  ),
  confidence: z.number().min(0).max(1).default(0.7).describe(
    'Confidence 0–1: 0.8–1.0 very high · 0.6–0.8 high · 0.3–0.6 medium · 0–0.3 low',
  ),
  tags: z.array(z.string().max(40)).max(10).default([]),
});

export type QueryInput = z.infer<typeof querySchema>;
export type StoreInput = z.infer<typeof storeSchema>;
export type QueryOutput = { found: boolean; count?: number; message?: string; memories: MemoryHit[] };
export type StoreOutput = { stored: boolean; type: string; preview: string; message: string };

// ─── Options

export interface NamsToolsOptions extends NamsConfig, NamsScope {
  /** When set, build a real entity graph on store (one extra model call). */
  extractionModel?: LanguageModel;
}

// ─── Factory

/** Returns `{ query_memory, store_memory }` ready to pass to `streamText({ tools })`. */
export function createNamsMemoryTools(options: NamsToolsOptions) {
  const client = makeClient(options);
  const scope: NamsScope = { userId: options.userId, conversationId: options.conversationId };
  const extractor = options.extractionModel ? createGraphExtractor(options.extractionModel) : undefined;

  let convIdPromise: Promise<string> | null = null;
  const getConvId = (): Promise<string> =>
    (convIdPromise ??= resolveConversation(client, options, scope));

  const query_memory = tool<QueryInput, QueryOutput>({
    description:
      'Search NAMS (Neo4j Agent Memory System) for context relevant to the current message. ' +
      'Call this FIRST every turn before answering.',
    inputSchema: zodSchema(querySchema),
    execute: async ({ query, limit }) => {
      const convId = await getConvId();
      const memories = await retrieveMemories(client, scope, convId, query, limit);
      if (memories.length === 0)
        return { found: false, message: 'No relevant memories found.', memories: [] };
      return { found: true, count: memories.length, memories };
    },
  });

  const store_memory = tool<StoreInput, StoreOutput>({
    description:
      'Persist important information to NAMS (Neo4j graph). ' +
      'Call this AFTER your response to save facts, preferences, and patterns.',
    inputSchema: zodSchema(storeSchema),
    execute: async ({ content, type, confidence, tags }) => {
      const convId = await getConvId();
      try {
        await storeMemory(client, convId, { content, type, confidence, tags }, { extractor });
        return {
          stored: true,
          type,
          preview: content.slice(0, 80),
          message: `Memory stored (${type}, confidence=${confidence})`,
        };
      } catch (err) {
        console.error('[nams] store_memory failed:', err);
        return { stored: false, type, preview: content.slice(0, 80), message: 'Failed to store memory.' };
      }
    },
  });

  return { query_memory, store_memory };
}

/**
 * Class-style alternative: construct once with shared config, call
 * `.forUser(userId, conversationId?)` per-request.
 */
export class NamsMemoryTools {
  constructor(private readonly base: Omit<NamsToolsOptions, 'userId' | 'conversationId'>) { }

  forUser(userId: string, conversationId?: string) {
    return createNamsMemoryTools({ ...this.base, userId, conversationId });
  }
}
