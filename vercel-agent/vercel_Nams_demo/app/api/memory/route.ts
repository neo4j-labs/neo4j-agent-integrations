// What NAMS holds for this user right now, read straight from the API so it works in every mode.
import { findExistingConversation, makeClient } from '@neo4j-labs/nams-ai-provider';
import { namsConfig } from '@/lib/mode';
import type { MemoryHit, MemorySnapshot, MemoryTab } from '@/types';
import { emptySnapshot } from '@/utils/message';

export const dynamic = 'force-dynamic';

const RECENT_LIMIT = 8;
const ENTITY_LIMIT = 8;
// listEntities has no user filter, so read a wider page and filter here.
const ENTITY_SCAN = 200;
const REASONING_LIMIT = 8;

type Client = ReturnType<typeof makeClient>;

export async function GET(request: Request): Promise<Response> {
  const params = new URL(request.url).searchParams;
  const userId = params.get('userId')?.trim();
  const query = params.get('q')?.trim() ?? '';

  if (!userId) return Response.json({ error: 'Missing userId' }, { status: 400 });
  const config = namsConfig();
  if (!config.apiKey) {
    return Response.json({ error: 'NAMS_API_KEY is not set. Check your .env.local file.' }, { status: 503 });
  }

  try {
    const client = makeClient(config);
    const conversationId = await findExistingConversation(client, config, { userId });

    const [context, entities, trace] = await Promise.all([
      conversationId ? client.shortTerm.getContext(conversationId) : null,
      userEntities(client, userId, query),
      reasoningTrace(client, conversationId),
    ]);

    const snapshot = emptySnapshot();

    // Hosted NAMS returns recent messages newest first; show them in chat order.
    snapshot.items.recent = [...(context?.recentMessages ?? [])]
      .filter(m => (m.role === 'user' || m.role === 'assistant') && !m.metadata?.namsKind)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp) || (a.role === 'user' ? -1 : 1))
      .slice(-RECENT_LIMIT)
      .map(m => ({ content: m.content, label: m.role }));

    snapshot.items.observations = (context?.observations ?? []).map(o => ({
      content: o.content,
      label: 'observation',
    }));

    snapshot.items.insights = (context?.reflections ?? []).map(r => ({
      content: r.content,
      label: 'reflection',
    }));

    snapshot.items.entities = entities.map(e => ({
      content: e.description ? `${e.name} — ${e.description}` : e.name,
      label: e.type || 'entity',
    }));

    snapshot.items.reasoning = trace.slice(-REASONING_LIMIT);

    for (const tab of Object.keys(snapshot.items) as MemoryTab[]) {
      snapshot.items[tab] = snapshot.items[tab].filter((hit: MemoryHit) => hit.content?.trim());
      snapshot.counts[tab] = snapshot.items[tab].length;
    }

    return Response.json(snapshot satisfies MemorySnapshot);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    console.error('[memory/GET] NAMS did not answer:', detail);
    return Response.json({ error: `Neo4j Agent Memory did not answer: ${detail}` }, { status: 502 });
  }
}

// Only this user's entities, the same ones query_memory can return; the workspace holds other users' too.
async function userEntities(client: Client, userId: string, query: string) {
  const found = query
    ? await client.longTerm.searchEntities(query, { limit: ENTITY_LIMIT, userId })
    : await client.longTerm.listEntities({ limit: ENTITY_SCAN });
  return found.filter(e => e.userId === userId).slice(0, ENTITY_LIMIT);
}

// The reasoning trail the hooks mode writes. A failure here must not hide the other tabs.
async function reasoningTrace(client: Client, conversationId: string | null): Promise<MemoryHit[]> {
  if (!conversationId) return [];
  try {
    const trace = await client.reasoning.getTraceByConversation(conversationId);
    return trace.steps.map(step => {
      const action = step.actionTaken || 'step';
      const detail = step.result?.trim();
      return { content: step.reasoning ?? '', label: detail ? `${action} · ${detail}` : action };
    });
  } catch {
    return [];
  }
}
