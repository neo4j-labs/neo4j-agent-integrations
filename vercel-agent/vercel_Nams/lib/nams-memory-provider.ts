import { MemoryClient } from '@neo4j-labs/agent-memory';
import { tool, zodSchema } from 'ai';
import { z } from 'zod';
import type { MemoryHit } from '@/types';

const DEFAULT_ENDPOINT = 'https://memory.neo4jlabs.com/v1';

export interface NamsMemoryOptions {
  apiKey: string;
  userId: string;
  conversationId?: string;
  workspaceId?: string;
  endpoint?: string;
}

export async function getOrCreateConversation(
  opts: NamsMemoryOptions,
): Promise<{ client: MemoryClient; convId: string }> {
  const client = makeClient(opts);
  if (opts.conversationId) {
    convCache.set(opts.userId, opts.conversationId);
    return { client, convId: opts.conversationId };
  }
  const convId = await resolveConversationId(client, opts.userId);
  return { client, convId };
}

export async function findExistingConversation(
  opts: NamsMemoryOptions,
): Promise<{ client: MemoryClient; convId: string } | null> {
  const client = makeClient(opts);
  if (opts.conversationId) return { client, convId: opts.conversationId };
  const cached = convCache.get(opts.userId);
  if (cached) return { client, convId: cached };
  try {
    const convs = await client.shortTerm.listConversations({ userId: opts.userId, limit: 1 });
    if (convs.length === 0) return null;
    const convId = convs[0].id;
    convCache.set(opts.userId, convId);
    console.log(`[NAMS] Found existing conversation ${convId} for userId=${opts.userId}`);
    return { client, convId };
  } catch {
    return null;
  }
}

function makeClient(opts: Omit<NamsMemoryOptions, 'userId'>): MemoryClient {
  const headers: Record<string, string> = {};
  if (opts.workspaceId) headers['X-Workspace-ID'] = opts.workspaceId;
  return new MemoryClient({
    endpoint: opts.endpoint ?? DEFAULT_ENDPOINT,
    apiKey:   opts.apiKey,
    headers,
  });
}

const convCache = new Map<string, string>();

async function resolveConversationId(client: MemoryClient, userId: string): Promise<string> {
  const cached = convCache.get(userId);
  if (cached) return cached;
  const t0   = Date.now();
  const conv = await client.shortTerm.createConversation({ userId });
  convCache.set(userId, conv.id);
  console.log(`[NAMS] New conversation → ${conv.id} for userId=${userId} (${Date.now() - t0}ms)`);
  return conv.id;
}

function trim(text: string, maxLen = 80): string {
  const s = text.replace(/\s+/g, ' ').trim();
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
}



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

type QueryInput  = z.infer<typeof querySchema>;
type StoreInput  = z.infer<typeof storeSchema>;
type QueryOutput = { found: boolean; count?: number; message?: string; memories: MemoryHit[] };
type StoreOutput = { stored: boolean; type: string; preview: string; message: string };

/**
 * Returns `{ query_memory, store_memory }`to pass to `streamText`
 */
// Search across all past conversations for a userId (cross-session retrieval)
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
    const hits: MemoryHit[] = [];

    // Search messages and reasoning steps from every past conversation
    await Promise.all(pastConvs.map(async (conv) => {
      try {
        const [messages, steps] = await Promise.all([
          client.shortTerm.searchMessages(query, {
            sessionId: conv.id,
            limit: 4,
            threshold: 0.35,
          }).catch(() => []),
          client.reasoning.listSteps(conv.id).catch(() => []),
        ]);

        for (const m of messages) {
          if (m.content && !seen.has(m.content)) {
            seen.add(m.content);
            hits.push({ content: m.content, source: 'conversation', type: 'cross-session' });
          }
        }

        for (const s of steps) {
          // Only keep actual AI response steps — skip tool-call steps (they contain JSON noise)
          if (s.actionTaken !== 'direct response') continue;
          if (s.reasoning && !seen.has(s.reasoning)) {
            seen.add(s.reasoning);
            hits.push({ content: s.reasoning, source: 'reasoning', type: 'cross-session-step' });
          }
        }
      } catch { /* skip failed conv */ }
    }));

    const sorted = hits.slice(0, limit);

    return sorted;
  } catch {
    return [];
  }
}

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

export function createNamsMemoryTools(options: NamsMemoryOptions) {
  const client = makeClient(options);
  let convId: string | null = convCache.get(options.userId) ?? null;

  async function getConvId(): Promise<string> {
    if (convId) return convId;
    convId = await resolveConversationId(client, options.userId);
    return convId;
  }

  const query_memory = tool<QueryInput, QueryOutput>({
    description:
      'Search NAMS (Neo4j Agent Memory System) for context relevant to the current message. ' +
      'Call this FIRST every turn before answering.',
    inputSchema: zodSchema(querySchema),
    execute: async ({ query, limit }: QueryInput): Promise<QueryOutput> => {
      console.log(`[NAMS:query] "${trim(query)}" (limit=${limit})`);
      const t0 = Date.now();
      const id = await getConvId();

      const [shortHits, longHits, reasoningSteps, crossSessionHits] = await Promise.all([
        client.shortTerm
          .searchMessages(query, { sessionId: id, limit, threshold: 0.4 })
          .catch(() => []),
        client.longTerm.searchEntities(query, { limit: 5 }).catch(() => []),
        client.reasoning.listSteps(id).catch(() => []),
        searchUserConversations(client, options.userId, id, query, 8),
      ]);

      // Deduplicate cross-session hits against current session hits
      const currentContents = new Set(shortHits.map(m => m.content));
      const uniqueCrossSession = crossSessionHits.filter(h => !currentContents.has(h.content));

      const cleanReasoningSteps = reasoningSteps.filter(s => s.actionTaken === 'direct response');

      // Long-term entities first (highest signal), then conversation hits, then cross-session, then reasoning
      const memories: MemoryHit[] = [
        ...longHits.map(e => ({
          content: e.description ?? e.name,
          source:  'long-term' as const,
          type:    'entity',
        })),
        ...shortHits.map(m => ({ content: m.content, source: 'conversation' as const, type: 'interaction' })),
        ...uniqueCrossSession,
        ...cleanReasoningSteps.map(s => ({
          content: s.reasoning,
          source:  'reasoning' as const,
          type:    'step',
        })),
      ];

      console.log(
        `[NAMS:query] ✓ ${shortHits.length} current + ${uniqueCrossSession.length} cross-session + ${longHits.length} long-term + ${cleanReasoningSteps.length}/${reasoningSteps.length} reasoning (${Date.now() - t0}ms)`,
      );
      memories.forEach((m, i) =>
        console.log(`[NAMS:query]   [${i + 1}] (${m.source}/${m.type}) "${trim(m.content)}"`),
      );

      if (memories.length === 0) return { found: false, message: 'No relevant memories found.', memories: [] };
      return { found: true, count: memories.length, memories };
    },
  });

  // store_memory (AFTER answering)
  const store_memory = tool<StoreInput, StoreOutput>({
    description:
      'Persist important information to NAMS (Neo4j graph). ' +
      'Call this AFTER your response to save facts, preferences, and patterns.',
    inputSchema: zodSchema(storeSchema),
    execute: async ({ content, type, confidence, tags }: StoreInput): Promise<StoreOutput> => {
      console.log(`[NAMS:store] ${type} (conf=${confidence}): "${trim(content)}"`);
      const t0 = Date.now();
      const id = await getConvId();

      if (type === 'interaction') {
        await client.shortTerm.addMessage(id, 'assistant', content);
        console.log(`[NAMS:store] ✓ short-term (${Date.now() - t0}ms)`);
      } else {
        const name = content.slice(0, 60) + (content.length > 60 ? '…' : '');
        await client.longTerm.addEntity(name, type, { description: content });
        console.log(`[NAMS:store] ✓ long-term "${trim(name)}" (${Date.now() - t0}ms)`);
      }

      void tags;
      return {
        stored:  true,
        type,
        preview: trim(content),
        message: `Memory stored (${type}, confidence=${confidence})`,
      };
    },
  });

  return { query_memory, store_memory };
}
