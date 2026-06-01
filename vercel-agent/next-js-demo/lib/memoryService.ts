import { MemoryClient } from '@neo4j-labs/agent-memory';

declare global {
  // eslint-disable-next-line no-var
  var __MEMORY_CLIENT__: MemoryClient | undefined;
  // eslint-disable-next-line no-var
  var __DEMO_CONVERSATION_ID__: string | undefined;
}

function readEnv(key: string): string | undefined {
  return process.env[key];
}

export function isMemoryConfigured(): boolean {
  return Boolean(readEnv('MEMORY_API_KEY'));
}

export function getMemoryConfigSourceLabel(): string {
  if (readEnv('MEMORY_API_KEY')) return 'MEMORY_API_KEY';
  return 'not-configured';
}

export function getMemoryClient(): MemoryClient | null {
  if (!isMemoryConfigured()) return null;

  if (!globalThis.__MEMORY_CLIENT__) {
    const apiKey = readEnv('MEMORY_API_KEY');
    const endpoint = readEnv('MEMORY_ENDPOINT');
    console.log('[memoryService] Initializing MemoryClient...');
    globalThis.__MEMORY_CLIENT__ = new MemoryClient(
      endpoint ? { apiKey, endpoint } : { apiKey },
    );
  }

  return globalThis.__MEMORY_CLIENT__;
}

/**
 * Returns a stable conversation ID for the demo session.
 * Creates a new conversation on first call and caches the ID across requests.
 */
export async function getDemoConversationId(): Promise<string | null> {
  const client = getMemoryClient();
  if (!client) return null;

  if (globalThis.__DEMO_CONVERSATION_ID__) {
    return globalThis.__DEMO_CONVERSATION_ID__;
  }

  try {
    const userId = readEnv('DEMO_AGENT_ID') || 'vercel-neo4j-demo';
    console.log('[memoryService] Creating demo conversation for userId:', userId);
    const conv = await client.shortTerm.createConversation({ userId });
    globalThis.__DEMO_CONVERSATION_ID__ = conv.id;
    console.log('[memoryService] Demo conversation created:', conv.id);
    return conv.id;
  } catch (error) {
    console.error('[memoryService] Failed to create demo conversation:', error);
    return null;
  }
}
