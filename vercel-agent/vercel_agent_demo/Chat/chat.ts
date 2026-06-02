
import { AsyncLocalStorage } from 'node:async_hooks';
import { MemoryClient } from '@neo4j-labs/agent-memory';
import { createMCPClient } from '@ai-sdk/mcp';
import type { MCPClient } from '@ai-sdk/mcp';

export interface McpToolRecord {
  tool: string;
  durationMs: number;
  ok: boolean;
}

const _mcpRecordStore = new AsyncLocalStorage<McpToolRecord[]>();

export async function runWithMcpTracker<T>(
  fn: () => Promise<T>,
): Promise<{ result: T; mcpTools: McpToolRecord[] }> {
  const records: McpToolRecord[] = [];
  const result = await _mcpRecordStore.run(records, fn);
  return { result, mcpTools: records };
}

const DEFAULT_SDK_ENDPOINT = 'https://memory.neo4jlabs.com/v1';
const GOOD_MATCH_THRESHOLD = 0.75;

let _sdkClient: MemoryClient | null = null;

function getSdkClient(): MemoryClient {
  const apiKey = process.env.MEMORY_API_KEY?.trim();
  if (!apiKey) {
    throw new Error('MEMORY_API_KEY is not configured. Copy .env.local.example → .env.local and set it.');
  }
  if (!_sdkClient) {
    const endpoint = process.env.MEMORY_ENDPOINT?.trim() || DEFAULT_SDK_ENDPOINT;
    const headers: Record<string, string> = {};
    const workspaceId = process.env.MEMORY_WORKSPACE_ID?.trim();
    if (workspaceId) headers['X-Workspace-ID'] = workspaceId;
    _sdkClient = new MemoryClient({ endpoint, apiKey, headers });
  }
  return _sdkClient;
}

export function getMemoryClient(): MemoryClient {
  return getSdkClient();
}

// ── MCP Tools 

let _mcpClientPromise: Promise<MCPClient> | null = null;

function getMcpClientPromise(): Promise<MCPClient> | null {
  const url = process.env.MCP_URL?.trim();
  if (!url) return null;

  if (!_mcpClientPromise) {
    const headers: Record<string, string> = {};
    const username = (process.env.MCP_NEO4J_USERNAME ?? process.env.NEO4J_USERNAME)?.trim();
    const password = (process.env.MCP_NEO4J_PASSWORD ?? process.env.NEO4J_PASSWORD)?.trim();
    if (username && password) {
      headers['Authorization'] = `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
    }

    _mcpClientPromise = createMCPClient({
      transport: { type: 'http', url, headers },
    }).catch((err) => {
      _mcpClientPromise = null;
      throw err;
    });
  }
  return _mcpClientPromise;
}

const MAX_TOOL_RESULT_CHARS = 50_000;
const TRUNCATION_NOTICE = '\n[...Result truncated. Use a more specific Cypher query with LIMIT and specific property selectors.]';

export async function getNeo4jMcpTools(): Promise<Record<string, unknown>> {
  const clientPromise = getMcpClientPromise();
  if (!clientPromise) return {};

  const client = await clientPromise;
  const rawTools = await client.tools();
  return Object.fromEntries(
    Object.entries(rawTools).map(([name, tool]) => [
      name,
      {
        ...tool,
        execute: async (...args: Parameters<typeof tool.execute>) => {
          const start = Date.now();
          let ok = false;
          try {
            const result = await tool.execute(...args);
            ok = true;
            const str = typeof result === 'string' ? result : JSON.stringify(result);
            if (str.length > MAX_TOOL_RESULT_CHARS) {
              return str.slice(0, MAX_TOOL_RESULT_CHARS) + TRUNCATION_NOTICE;
            }
            return result;
          } finally {
            _mcpRecordStore.getStore()?.push({ tool: name, durationMs: Date.now() - start, ok });
          }
        },
      },
    ]),
  );
}


export async function ensureConversation(
  sessionId: string,
  existingConversationId?: string,
): Promise<string> {
  if (existingConversationId) return existingConversationId;
  try {
    const conv = await getSdkClient().shortTerm.createConversation({ userId: sessionId });
    return conv.id;
  } catch (err) {
    console.error('[chat] Failed to create conversation for session', sessionId, err);
    throw err;
  }
}

export async function getConversationContext(conversationId: string): Promise<{
  recentMessages: Array<{ role: string; content: string }>;
  reflections: Array<{ content: string }>;
  observations: Array<{ content: string }>;
}> {
  return getSdkClient().shortTerm.getContext(conversationId) as any;
}

export async function addMessage(
  conversationId: string,
  role: 'user' | 'assistant',
  content: string,
): Promise<void> {
  await getSdkClient().shortTerm.addMessage(conversationId, role, content);
}

export async function searchMemoryContext(
  conversationId: string,
  query: string,
  limit = 5,
): Promise<string[]> {
  if (!query.trim()) return [];
  try {
    const results = await getSdkClient().shortTerm.searchMessages(query, {
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

export async function searchUserMemoryContext(
  userId: string,
  query: string,
  limit = 3,
): Promise<string[]> {
  if (!query.trim()) return [];
  const apiKey = process.env.MEMORY_API_KEY?.trim();
  if (!apiKey) return [];

  try {
    const restBase = process.env.MEMORY_ENDPOINT?.trim() || DEFAULT_SDK_ENDPOINT;
    const url = `${restBase}/short-term/search?user_id=${encodeURIComponent(userId)}&query=${encodeURIComponent(query)}&limit=${limit}`;
    const res = await fetch(url, {
      method: 'GET',
      headers: { Authorization: `Bearer ${apiKey}` },
    });
    if (!res.ok) {
      console.warn(`[chat] REST user search failed with ${res.status}:`, await res.text());
      return [];
    }
    const data = await res.json();
    const results: unknown[] = Array.isArray(data) ? data : (data.messages ?? data.results ?? []);
    return results
      .map((m: any) => m.content ?? m.text ?? (typeof m === 'string' ? m : null))
      .filter(Boolean)
      .slice(0, limit);
  } catch (err) {
    console.warn('[chat] searchUserMemoryContext failed:', err);
    return [];
  }
}

export async function searchPreviousConversations(
  conversationIds: string[],
  query: string,
  limit = 3,
): Promise<string[]> {
  if (!query.trim() || !conversationIds.length) return [];

  const results: string[] = [];
  const seen = new Set<string>();

  for (const convId of conversationIds) {
    if (results.length >= limit) break;
    try {
      const matches = await searchMemoryContext(convId, query, Math.ceil(limit / conversationIds.length) + 1);
      for (const match of matches) {
        if (!seen.has(match) && results.length < limit) {
          results.push(match);
          seen.add(match);
        }
      }
    } catch (err) {
      console.warn(`[chat] Failed to search conversation ${convId}:`, err);
    }
  }
  return results;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  try {
    await getSdkClient().shortTerm.deleteConversation(conversationId);
    console.log(`[chat] Successfully deleted conversation ${conversationId}`);
  } catch (err) {
    console.error(`[chat] Error deleting conversation ${conversationId}:`, err);
    throw err;
  }
}
