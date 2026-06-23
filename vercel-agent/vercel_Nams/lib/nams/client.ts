import { MemoryClient } from '@neo4j-labs/agent-memory';

export const DEFAULT_ENDPOINT = 'https://memory.neo4jlabs.com/v1';

export interface NamsConfig {
  apiKey: string;
  endpoint?: string;
  workspaceId?: string;
}

export interface NamsScope {
  userId: string;
  /** Pin to an existing NAMS conversation id (e.g. sent back from a previous response). */
  conversationId?: string;
}

export type MemorySource = 'long-term' | 'conversation' | 'cross-session' | 'reasoning';
export type MemoryType = 'fact' | 'interaction' | 'pattern' | 'user_preference';

export interface MemoryHit {
  content: string;
  source: MemorySource;
  type: string;
  score?: number;
}

export interface StoreInput {
  content: string;
  type: MemoryType;
  confidence?: number;
  tags?: string[];
}

export type GraphExtractor = (client: MemoryClient, input: StoreInput) => Promise<void>;

// ─── Client factory ───────────────────────────────────────────────────────────

export function makeClient(config: NamsConfig): MemoryClient {
  const headers: Record<string, string> = {};
  if (config.workspaceId) headers['X-Workspace-ID'] = config.workspaceId;
  return new MemoryClient({
    endpoint: config.endpoint ?? DEFAULT_ENDPOINT,
    apiKey: config.apiKey,
    headers,
  });
}

// ─── Conversation resolution ──────────────────────────────────────────────────
// In-process cache keyed by workspace + user so multi-tenant deployments can't
// collide. Does NOT survive Vercel cold starts — warm-instance optimisation only.

const convCache = new Map<string, string>();

function cacheKey(config: NamsConfig, userId: string): string {
  return `${config.workspaceId ?? 'default'}:${userId}`;
}

/**
 * Resolve a conversation id. Precedence:
 *   1. explicit scope.conversationId
 *   2. warm-instance cache
 *   3. the user's most recent existing conversation in NAMS (GET)
 *   4. create a new one (CREATE)
 */
export async function resolveConversation(
  client: MemoryClient,
  config: NamsConfig,
  scope: NamsScope,
): Promise<string> {
  const key = cacheKey(config, scope.userId);

  if (scope.conversationId) {
    convCache.set(key, scope.conversationId);
    return scope.conversationId;
  }

  const cached = convCache.get(key);
  if (cached) return cached;

  try {
    const convs = await client.shortTerm.listConversations({ userId: scope.userId, limit: 1 });
    if (convs.length > 0) {
      convCache.set(key, convs[0].id);
      console.log(`[nams] resumed conversation ${convs[0].id} for userId=${scope.userId}`);
      return convs[0].id;
    }
  } catch (err) {
    console.warn('[nams] listConversations failed, creating new conversation:', err);
  }

  const conv = await client.shortTerm.createConversation({ userId: scope.userId });
  convCache.set(key, conv.id);
  console.log(`[nams] created conversation ${conv.id} for userId=${scope.userId}`);
  return conv.id;
}

// ─── Retrieval ────────────────────────────────────────────────────────────────

const RETRIEVAL = {
  currentThreshold: 0.4,
  crossThreshold: 0.4,
  maxReasoning: 6,   // cap reasoning steps so context can't grow unbounded
  maxTotal: 12,
};

function deduplicatePush(hits: MemoryHit[], seen: Set<string>, hit: MemoryHit): void {
  const k = hit.content?.trim();
  if (!k || seen.has(k)) return;
  seen.add(k);
  hits.push(hit);
}

async function searchPastConversations(
  client: MemoryClient,
  userId: string,
  currentConvId: string,
  query: string,
): Promise<MemoryHit[]> {
  const seen = new Set<string>();
  const hits: MemoryHit[] = [];

  let convs: Array<{ id: string }>;
  try {
    convs = await client.shortTerm.listConversations({ userId, limit: 20 });
  } catch (err) {
    console.warn('[nams] cross-session listConversations failed:', err);
    return hits;
  }

  const past = convs.filter(c => c.id !== currentConvId);
  await Promise.all(
    past.map(async (conv) => {
      const [messages, steps] = await Promise.all([
        client.shortTerm
          .searchMessages(query, { sessionId: conv.id, limit: 4, threshold: RETRIEVAL.crossThreshold })
          .catch((e: unknown) => { console.warn('[nams] cross-session searchMessages failed:', e); return [] as any[]; }),
        client.reasoning.listSteps(conv.id)
          .catch((e: unknown) => { console.warn('[nams] cross-session listSteps failed:', e); return [] as any[]; }),
      ]);

      for (const m of messages) {
        deduplicatePush(hits, seen, { content: m.content, source: 'cross-session', type: 'message', score: m.score });
      }
      for (const s of steps) {
        if (s.actionTaken !== 'direct response' || !s.reasoning) continue;
        deduplicatePush(hits, seen, { content: s.reasoning, source: 'cross-session', type: 'reasoning', score: s.score });
      }
    }),
  );

  return hits;
}

/**
 * Search all four NAMS sources in parallel, dedupe, rank, and cap.
 * Priority (when no score): long-term > current conversation > cross-session > reasoning.
 * When scores are present the results are sorted by score descending.
 */
export async function retrieveMemories(
  client: MemoryClient,
  scope: NamsScope,
  convId: string,
  query: string,
  limit = 5,
): Promise<MemoryHit[]> {
  const [shortHits, longHits, reasoningSteps, crossHits] = await Promise.all([
    client.shortTerm
      .searchMessages(query, { sessionId: convId, limit, threshold: RETRIEVAL.currentThreshold })
      .catch((e: unknown) => { console.warn('[nams] searchMessages failed:', e); return [] as any[]; }),
    client.longTerm.searchEntities(query, { limit: 5 })
      .catch((e: unknown) => { console.warn('[nams] searchEntities failed:', e); return [] as any[]; }),
    client.reasoning.listSteps(convId)
      .catch((e: unknown) => { console.warn('[nams] listSteps failed:', e); return [] as any[]; }),
    searchPastConversations(client, scope.userId, convId, query),
  ]);

  const seen = new Set<string>();
  const hits: MemoryHit[] = [];

  for (const e of longHits) {
    deduplicatePush(hits, seen, {
      content: e.description ?? e.name,
      source: 'long-term',
      type: e.type ?? 'entity',
      score: e.score,
    });
  }
  for (const m of shortHits) {
    deduplicatePush(hits, seen, { content: m.content, source: 'conversation', type: 'message', score: m.score });
  }
  for (const h of crossHits) deduplicatePush(hits, seen, h);

  const reasoning = (reasoningSteps as any[])
    .filter(s => s.actionTaken === 'direct response' && s.reasoning)
    .slice(0, RETRIEVAL.maxReasoning);
  for (const s of reasoning) {
    deduplicatePush(hits, seen, { content: s.reasoning, source: 'reasoning', type: 'step', score: s.score });
  }

  const hasScores = hits.some(h => typeof h.score === 'number');
  const ranked = hasScores ? [...hits].sort((a, b) => (b.score ?? 0) - (a.score ?? 0)) : hits;
  return ranked.slice(0, RETRIEVAL.maxTotal);
}

// ─── Storage ──────────────────────────────────────────────────────────────────

function entityName(content: string, max = 60): string {
  const s = content.replace(/\s+/g, ' ').trim();
  return s.length > max ? s.slice(0, max) + '…' : s;
}

/**
 * Persist a memory:
 *   - `interaction`              → short-term conversation thread
 *   - fact / preference / pattern → long-term graph
 *
 * If `extractor` is provided, real entities + relationships are extracted
 * so the graph actually forms. Otherwise falls back to a single entity node.
 */
export async function storeMemory(
  client: MemoryClient,
  convId: string,
  input: StoreInput,
  opts: { extractor?: GraphExtractor } = {},
): Promise<void> {
  if (input.type === 'interaction') {
    await client.shortTerm.addMessage(convId, 'assistant', input.content);
    return;
  }

  if (opts.extractor) {
    try {
      await opts.extractor(client, input);
      return;
    } catch (err) {
      console.warn('[nams] graph extraction failed, falling back to flat entity:', err);
    }
  }

  const name = entityName(input.content);
  let entity = await client.longTerm.getEntityByName(name).catch(() => null);
  if (!entity) {
    entity = await client.longTerm.addEntity(name, input.type, { description: input.content });
  }
  if (entity?.id && input.confidence !== undefined) {
    await client.longTerm
      .setEntityFeedback(entity.id, { userScore: input.confidence, confirmed: input.confidence >= 0.8 })
      .catch(() => { });
  }
}
