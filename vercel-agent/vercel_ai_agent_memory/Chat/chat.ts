
import { MemoryClient } from '@neo4j-labs/agent-memory';

const DEFAULT_MEMORY_ENDPOINT = 'https://memory.neo4jlabs.com/v1';
const GOOD_MATCH_THRESHOLD = 0.75;

let _client: MemoryClient | null = null;

function getMemoryApiKey(): string | null {
  return process.env.MEMORY_API_KEY?.trim() || null;
}

function getMemoryEndpoint(): string {
  return process.env.MEMORY_ENDPOINT?.trim() || DEFAULT_MEMORY_ENDPOINT;
}

/** Returns the shared MemoryClient, initialising it lazily on first call. Throws if MEMORY_API_KEY is absent. */
export function getMemoryClient(): MemoryClient {
  const apiKey = getMemoryApiKey();
  if (!apiKey) {
    throw new Error('MEMORY_API_KEY is not configured. Copy .env.local.example → .env.local and set it.');
  }
  if (!_client) {
    _client = new MemoryClient({ endpoint: getMemoryEndpoint(), apiKey });
  }
  return _client;
}

export async function ensureConversation(
  sessionId: string,
  existingConversationId?: string,
): Promise<string> {
  if (existingConversationId) {
    return existingConversationId;
  }

  const client = getMemoryClient();
  try {
    const conv = await client.shortTerm.createConversation({ userId: sessionId });
    return conv.id;
  } catch (err) {
    console.error('[chat] Failed to create NAMS conversation for session', sessionId, err);
    throw err;
  }
}

export async function searchMemoryContext(
  conversationId: string,
  query: string,
  limit = 5,
): Promise<string[]> {
  if (!query.trim()) return [];
  try {
    const client = getMemoryClient();
    const results = await client.shortTerm.searchMessages(query, {
      sessionId: conversationId,
      limit,
      threshold: GOOD_MATCH_THRESHOLD,
    });
    return results.map((m) => m.content).filter(Boolean);
  } catch (err) {
    console.warn('[chat] searchMessages failed:', err);
    return [];
  }
}
