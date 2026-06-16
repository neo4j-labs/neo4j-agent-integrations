import { MemoryClient } from '@neo4j-labs/agent-memory';
import { tool, zodSchema } from 'ai';
import { z } from 'zod';
import type { MemoryHit } from '@/types';

const DEFAULT_ENDPOINT = 'https://memory.neo4jlabs.com/v1';
const MAX_REASONING_STEPS = 15;

export interface NamsMemoryOptions {
  apiKey: string;
  userId: string;
  conversationId?: string;
  workspaceId?: string;
  endpoint?: string;
}

// Cache helpers

const convCache = new Map<string, string>();

/** Composite key so multi-tenant deployments (different workspaceIds) never collide. */
function cacheKey(userId: string, workspaceId?: string): string {
  return workspaceId ? `${workspaceId}:${userId}` : userId;
}

// Public conversation helpers

export async function getOrCreateConversation(
  opts: NamsMemoryOptions,
): Promise<{ client: MemoryClient; convId: string }> {
  const client = makeClient(opts);
  if (opts.conversationId) {
    convCache.set(cacheKey(opts.userId, opts.workspaceId), opts.conversationId);
    return { client, convId: opts.conversationId };
  }
  const convId = await resolveConversationId(client, opts.userId, opts.workspaceId);
  return { client, convId };
}

export async function findExistingConversation(
  opts: NamsMemoryOptions,
): Promise<{ client: MemoryClient; convId: string } | null> {
  const client = makeClient(opts);
  if (opts.conversationId) return { client, convId: opts.conversationId };
  const cached = convCache.get(cacheKey(opts.userId, opts.workspaceId));
  if (cached) return { client, convId: cached };
  try {
    const convs = await client.shortTerm.listConversations({ userId: opts.userId, limit: 1 });
    if (convs.length === 0) return null;
    const convId = convs[0].id;
    convCache.set(cacheKey(opts.userId, opts.workspaceId), convId);
    console.log(`[NAMS] Found existing conversation ${convId} for userId=${opts.userId}`);
    return { client, convId };
  } catch {
    return null;
  }
}

// ─── Internal helpers

function makeClient(opts: Omit<NamsMemoryOptions, 'userId'>): MemoryClient {
  const headers: Record<string, string> = {};
  if (opts.workspaceId) headers['X-Workspace-ID'] = opts.workspaceId;
  return new MemoryClient({
    endpoint: opts.endpoint ?? DEFAULT_ENDPOINT,
    apiKey: opts.apiKey,
    headers,
  });
}

/** List existing conversations first; only create when none exist. */
async function resolveConversationId(
  client: MemoryClient,
  userId: string,
  workspaceId?: string,
): Promise<string> {
  const key = cacheKey(userId, workspaceId);
  const cached = convCache.get(key);
  if (cached) return cached;

  try {
    const convs = await client.shortTerm.listConversations({ userId, limit: 1 });
    if (convs.length > 0) {
      const convId = convs[0].id;
      convCache.set(key, convId);
      console.log(`[NAMS] Resumed conversation ${convId} for userId=${userId}`);
      return convId;
    }
  } catch { /* fall through to create */ }

  const t0 = Date.now();
  const conv = await client.shortTerm.createConversation({ userId });
  convCache.set(key, conv.id);
  console.log(`[NAMS] New conversation → ${conv.id} for userId=${userId} (${Date.now() - t0}ms)`);
  return conv.id;
}

function trim(text: string, maxLen = 80): string {
  const s = text.replace(/\s+/g, ' ').trim();
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
}

/**
 * Derive a stable, meaningful entity name from free-form content.
 * Strips common sentence-starter phrases so the name isn't a truncated sentence.
 */
function deriveEntityName(content: string): string {
  const first = content.split(/[.!?]/)[0].trim();
  const name = first.replace(/^(the user|i am|i'm)\s+/i, '').trim() || first;
  return name.length <= 80 ? name : name.slice(0, 79) + '…';
}

// ─── Zod schemas

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
  confidence: z.number().min(0).max(1).describe(
    'Confidence 0–1: 0.8–1.0 very high · 0.6–0.8 high · 0.3–0.6 medium · 0–0.3 low',
  ),
  tags: z.array(z.string().max(40)).max(10).default([]),
});

export type QueryInput = z.infer<typeof querySchema>;
export type StoreInput = z.infer<typeof storeSchema>;
export type QueryOutput = { found: boolean; count?: number; message?: string; memories: MemoryHit[] };
export type StoreOutput = { stored: boolean; type: string; preview: string; message: string };

// ─── Cross-session search

async function searchUserConversations(
  client: MemoryClient,
  userId: string,
  currentConvId: string,
  query: string,
  limit: number,
): Promise<MemoryHit[]> {
  try {
    const convs = await client.shortTerm.listConversations({ userId, limit: 20 });
    const pastConvs = convs.filter(c => c.id !== currentConvId);
    if (pastConvs.length === 0) return [];

    console.log(`[NAMS:query] Searching ${pastConvs.length} past conversation(s) for userId=${userId}`);
    const seen = new Set<string>();
    const hits: (MemoryHit & { score: number })[] = [];

    await Promise.all(pastConvs.map(async (conv) => {
      try {
        const [messages, steps] = await Promise.all([
          client.shortTerm.searchMessages(query, {
            sessionId: conv.id,
            limit: 4,
            threshold: 0.4,
          }).catch(() => []),
          client.reasoning.listSteps(conv.id).catch(() => []),
        ]);

        // NAMS returns messages ordered by descending similarity; use position as proxy score
        messages.forEach((m, i) => {
          if (m.content && !seen.has(m.content)) {
            seen.add(m.content);
            hits.push({
              content: m.content,
              source: 'conversation',
              type: 'cross-session',
              score: 1 - i / Math.max(messages.length, 1),
            });
          }
        });

        for (const s of steps) {
          if (s.actionTaken !== 'direct response') continue;
          if (s.reasoning && !seen.has(s.reasoning)) {
            seen.add(s.reasoning);
            hits.push({ content: s.reasoning, source: 'reasoning', type: 'cross-session-step', score: 0.3 });
          }
        }
      } catch { /* skip failed conv */ }
    }));

    return hits
      .sort((a, b) => b.score - a.score)
      .slice(0, limit);
  } catch {
    return [];
  }
}

// ─── Core query / store logic

/**
 * NamsMemoryProvider — Vercel AI SDK memory provider backed by Neo4j.
 *
 * Usage (per-request, in a Next.js route handler):
 *
 *   const memory = new NamsMemoryProvider({ apiKey: process.env.MEMORY_API_KEY! });
 *
 *   const result = streamText({
 *     model: openai('gpt-4o-mini'),
 *     system: SYSTEM_PROMPT,
 *     messages,
 *     tools: memory.forUser(userId).tools(),
 *   });
 */
export class NamsMemoryProvider {
  private readonly opts: NamsMemoryOptions;

  constructor(opts: NamsMemoryOptions) {
    this.opts = opts;
  }

  /** Return a provider scoped to a specific user (call this per-request). */
  forUser(userId: string, conversationId?: string): NamsMemoryProvider {
    return new NamsMemoryProvider({ ...this.opts, userId, conversationId });
  }

  /** Returns `{ query_memory, store_memory }` ready to pass to `streamText`. */
  tools() {
    return createNamsMemoryTools(this.opts);
  }
}

/** Core query logic — callable by both tool() wrappers and the provider middleware. */
export async function executeQueryMemory(
  client: MemoryClient,
  userId: string,
  convId: string,
  { query, limit = 5 }: QueryInput,
): Promise<QueryOutput> {
  console.log(`[NAMS:query] "${trim(query)}" (limit=${limit})`);
  const t0 = Date.now();

  const [shortHits, longHits, reasoningSteps, crossSessionHits] = await Promise.all([
    client.shortTerm
      .searchMessages(query, { sessionId: convId, limit, threshold: 0.4 })
      .catch(() => []),
    client.longTerm.searchEntities(query, { limit: 5 }).catch(() => []),
    client.reasoning.listSteps(convId).catch(() => []),
    searchUserConversations(client, userId, convId, query, 8),
  ]);

  const currentContents = new Set(shortHits.map(m => m.content));
  const uniqueCrossSession = crossSessionHits.filter(h => !currentContents.has(h.content));

  // Cap reasoning to the most recent N direct-response steps
  const cleanReasoningSteps = reasoningSteps
    .filter(s => s.actionTaken === 'direct response')
    .slice(-MAX_REASONING_STEPS);

  const memories: MemoryHit[] = [
    // Long-term entities: use entity confidence when available; otherwise position-based score
    ...longHits.map((e, i) => ({
      content: e.description ?? e.name,
      source: 'long-term' as const,
      type: 'entity',
      score: e.confidence ?? (1 - i / Math.max(longHits.length, 1)),
    })),
    // Current-session messages: NAMS returns by descending similarity, so position ≈ relevance
    ...shortHits.map((m, i) => ({
      content: m.content,
      source: 'conversation' as const,
      type: 'interaction',
      score: 1 - i / Math.max(shortHits.length, 1),
    })),
    ...uniqueCrossSession,
    // Reasoning steps: background context, always ranked last
    ...cleanReasoningSteps.map(s => ({
      content: s.reasoning,
      source: 'reasoning' as const,
      type: 'step',
      score: 0.2,
    })),
  ];

  // Surface highest-confidence / most-relevant hits first
  memories.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

  console.log(
    `[NAMS:query] ✓ ${shortHits.length} current + ${uniqueCrossSession.length} cross-session + ` +
    `${longHits.length} long-term + ${cleanReasoningSteps.length}/${reasoningSteps.length} reasoning (${Date.now() - t0}ms)`,
  );
  memories.forEach((m, i) =>
    console.log(`[NAMS:query]   [${i + 1}] (${m.source}/${m.type}, score=${(m.score ?? 0).toFixed(2)}) "${trim(m.content)}"`),
  );

  if (memories.length === 0) return { found: false, message: 'No relevant memories found.', memories: [] };
  return { found: true, count: memories.length, memories };
}

/** Core store logic — callable by both tool() wrappers and the provider middleware. */
export async function executeStoreMemory(
  client: MemoryClient,
  _userId: string,
  convId: string,
  { content, type, confidence, tags }: StoreInput,
): Promise<StoreOutput> {
  console.log(`[NAMS:store] ${type} (conf=${confidence}): "${trim(content)}"`);
  const t0 = Date.now();

  if (type === 'interaction') {
    // Persist confidence + tags as message metadata so they're searchable later
    await client.shortTerm.addMessage(convId, 'assistant', content, {
      metadata: { confidence, ...(tags.length ? { tags } : {}) },
    });
    console.log(`[NAMS:store] ✓ short-term (${Date.now() - t0}ms)`);
  } else {
    // Map our schema type to the NAMS hosted entity taxonomy
    const namsType = type === 'user_preference' ? 'custom' : 'concept';
    const entityName = deriveEntityName(content);

    // Deduplicate: check if this entity already exists before creating a new node
    let entity = await client.longTerm.getEntityByName(entityName).catch(() => null);
    if (!entity) {
      entity = await client.longTerm.addEntity(entityName, namsType, { description: content });
      console.log(`[NAMS:store] ✓ long-term entity "${trim(entityName)}" (${Date.now() - t0}ms)`);
    } else {
      console.log(`[NAMS:store] ✓ deduped entity "${trim(entityName)}" id=${entity.id}`);
    }

    // Persist the model's confidence score as entity feedback
    if (entity?.id) {
      await client.longTerm
        .setEntityFeedback(entity.id, { userScore: confidence, confirmed: confidence >= 0.8 })
        .catch(() => { });
    }
  }

  return {
    stored: true,
    type,
    preview: trim(content),
    message: `Memory stored (${type}, confidence=${confidence})`,
  };
}

export function createNamsMemoryTools(options: NamsMemoryOptions) {
  const client = makeClient(options);
  let convId: string | null =
    options.conversationId ?? convCache.get(cacheKey(options.userId, options.workspaceId)) ?? null;

  async function getConvId(): Promise<string> {
    if (convId) return convId;
    convId = await resolveConversationId(client, options.userId, options.workspaceId);
    return convId;
  }

  const query_memory = tool<QueryInput, QueryOutput>({
    description:
      'Search NAMS (Neo4j Agent Memory System) for context relevant to the current message. ' +
      'Call this FIRST every turn before answering.',
    inputSchema: zodSchema(querySchema),
    execute: async (input: QueryInput) => {
      return executeQueryMemory(client, options.userId, await getConvId(), input);
    },
  });

  const store_memory = tool<StoreInput, StoreOutput>({
    description:
      'Persist important information to NAMS (Neo4j graph). ' +
      'Call this AFTER your response to save facts, preferences, and patterns.',
    inputSchema: zodSchema(storeSchema),
    execute: async (input: StoreInput) => {
      return executeStoreMemory(client, options.userId, await getConvId(), input);
    },
  });

  return { query_memory, store_memory };
}
