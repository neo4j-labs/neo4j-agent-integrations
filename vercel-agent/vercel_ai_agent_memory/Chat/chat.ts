
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

/**
 * Returns an existing NAMS conversation ID (when the client already has one stored)
 * or creates a brand-new conversation for this session.
 *
 * We intentionally avoid `listConversations` because the NAMS API does not
 * reliably filter by userId, which would cause a new session to inherit
 * messages from an unrelated older session.
 */
export async function ensureConversation(
  sessionId: string,
  existingConversationId?: string,
): Promise<string> {
  // If the client already has a conversationId for this session, trust it.
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

/**
 * Semantic search over stored messages in a conversation.
 * Returns the content strings of matching messages above the similarity threshold.
 * Used to surface long-term relevant context beyond the recent-messages window.
 */
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
