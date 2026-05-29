
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
const DEFAULT_MCP_URL = 'https://memory.neo4jlabs.com/mcp';
const GOOD_MATCH_THRESHOLD = 0.75;

function useMcpTransport(): boolean {
  return process.env.MEMORY_TRANSPORT?.trim().toLowerCase() === 'mcp';
}


let _sdkClient: MemoryClient | null = null;

function getSdkClient(): MemoryClient {
  const apiKey = process.env.MEMORY_API_KEY?.trim();
  if (!apiKey) {
    throw new Error('MEMORY_API_KEY is not configured. Copy .env.local.example → .env.local and set it.');
  }
  if (!_sdkClient) {
    const endpoint = process.env.MEMORY_ENDPOINT?.trim() || DEFAULT_SDK_ENDPOINT;
    _sdkClient = new MemoryClient({ endpoint, apiKey });
  }
  return _sdkClient;
}

export function getMemoryClient(): MemoryClient {
  return getSdkClient();
}

function getMcpAuthHeader(): string {
  const username = process.env.NEO4J_USERNAME?.trim();
  const password = process.env.NEO4J_PASSWORD?.trim();
  if (username && password) {
    return `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
  }

  throw new Error(
    'Neo4j MCP tools require auth. Set NEO4J_USERNAME + NEO4J_PASSWORD (Basic).',
  );
}

let _mcpClientPromise: Promise<MCPClient> | null = null;

function getMcpClientPromise(): Promise<MCPClient> {
  if (!_mcpClientPromise) {
    const url = process.env.MCP_URL?.trim() || DEFAULT_MCP_URL;
    _mcpClientPromise = createMCPClient({
      transport: {
        type: 'http',
        url,
        headers: { Authorization: getMcpAuthHeader() },
      },
    }).catch((err) => {
      _mcpClientPromise = null;
      throw err;
    });
  }
  return _mcpClientPromise;
}

const MAX_TOOL_RESULT_CHARS = 50_000;
const TRUNCATION_NOTICE = '\n[...Result truncated. Use a more specific Cypher query with LIMIT and specific property selectors.]';

export async function getNeo4jMcpTools() {
  const client = await getMcpClientPromise();
  const rawTools = await client.tools();
  return Object.fromEntries(
    Object.entries(rawTools).map(([name, tool]) => [
      name,
      {
        ...tool,
        execute: async (...args: Parameters<typeof tool.execute>) => {
          const result = await tool.execute(...args);
          const str = typeof result === 'string' ? result : JSON.stringify(result);
          if (str.length > MAX_TOOL_RESULT_CHARS) {
            return str.slice(0, MAX_TOOL_RESULT_CHARS) + TRUNCATION_NOTICE;
          }
          return result;
        },
      },
    ]),
  );
}

/** @deprecated use getNeo4jMcpTools */
export const getMemoryTools = getNeo4jMcpTools;

async function callMcpTool(name: string, args: Record<string, unknown>): Promise<unknown> {
  const client = await getMcpClientPromise();
  const start = Date.now();
  let ok = false;
  try {
    const result = await (client as any).callTool({ name, args });
    if (result?.isError) {
      throw new Error(`MCP tool '${name}' error: ${JSON.stringify(result.content)}`);
    }
    ok = true;
    const text = (result?.content ?? []).find((c: any) => c.type === 'text')?.text;
    if (text) {
      try { return JSON.parse(text); } catch { return text; }
    }
    return result?.structuredContent ?? result;
  } finally {
    _mcpRecordStore.getStore()?.push({ tool: name, durationMs: Date.now() - start, ok });
  }
}

export async function ensureConversation(
  sessionId: string,
  existingConversationId?: string,
): Promise<string> {
  if (existingConversationId) return existingConversationId;

  try {
    if (useMcpTransport()) {
      try {
        const conv = (await callMcpTool('memory_create_conversation', { user_id: sessionId })) as { id: string };
        return conv.id;
      } catch (mcpErr: any) {
        // Fall back to SDK if MCP tool not found
        if (mcpErr?.code === -32602 || mcpErr?.message?.includes('not found')) {
          console.warn('[chat] MCP tool not found, falling back to SDK client');
          const conv = await getSdkClient().shortTerm.createConversation({ userId: sessionId });
          return conv.id;
        }
        throw mcpErr;
      }
    } else {
      const conv = await getSdkClient().shortTerm.createConversation({ userId: sessionId });
      return conv.id;
    }
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
  if (useMcpTransport()) {
    try {
      return (await callMcpTool('memory_get_context', { conversation_id: conversationId })) as any;
    } catch (mcpErr: any) {
      // Fall back to SDK if MCP tool not found
      if (mcpErr?.code === -32602 || mcpErr?.message?.includes('not found')) {
        console.warn('[chat] MCP tool not found, falling back to SDK client');
        return getSdkClient().shortTerm.getContext(conversationId) as any;
      }
      throw mcpErr;
    }
  } else {
    return getSdkClient().shortTerm.getContext(conversationId) as any;
  }
}

export async function addMessage(
  conversationId: string,
  role: 'user' | 'assistant',
  content: string,
): Promise<void> {
  if (useMcpTransport()) {
    try {
      await callMcpTool('memory_add_messages', {
        conversation_id: conversationId,
        messages: [{ role, content }],
      });
    } catch (mcpErr: any) {
      // Fall back to SDK if MCP tool not found
      if (mcpErr?.code === -32602 || mcpErr?.message?.includes('not found')) {
        console.warn('[chat] MCP tool not found, falling back to SDK client');
        await getSdkClient().shortTerm.addMessage(conversationId, role, content);
      } else {
        throw mcpErr;
      }
    }
  } else {
    await getSdkClient().shortTerm.addMessage(conversationId, role, content);
  }
}

export async function searchMemoryContext(
  conversationId: string,
  query: string,
  limit = 5,
): Promise<string[]> {
  if (!query.trim()) return [];
  try {
    if (useMcpTransport()) {
      try {
        const results = (await callMcpTool('memory_search_messages', {
          conversation_id: conversationId,
          query,
          limit,
        })) as Array<{ content: string }>;
        return Array.isArray(results) ? results.map((m) => m.content).filter(Boolean) : [];
      } catch (mcpErr: any) {
        // Fall back to SDK if MCP tool not found
        if (mcpErr?.code === -32602 || mcpErr?.message?.includes('not found')) {
          console.warn('[chat] MCP tool not found, falling back to SDK client');
          const results = await getSdkClient().shortTerm.searchMessages(query, {
            sessionId: conversationId,
            limit,
            threshold: GOOD_MATCH_THRESHOLD,
          });
          return results.map((m) => m.content).filter(Boolean);
        }
        throw mcpErr;
      }
    } else {
      const results = await getSdkClient().shortTerm.searchMessages(query, {
        sessionId: conversationId,
        limit,
        threshold: GOOD_MATCH_THRESHOLD,
      });
      return results.map((m) => m.content).filter(Boolean);
    }
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
  try {
    if (useMcpTransport()) {
      const authHeader = getMcpAuthHeader();
      const restBase = process.env.MEMORY_REST_URL?.trim() || 'https://memory.neo4jlabs.com/v1';
      const url = `${restBase}/short-term/search?user_id=${encodeURIComponent(userId)}&query=${encodeURIComponent(query)}&limit=${limit}`;
      
      try {
        const res = await fetch(url, {
          method: 'GET',
          headers: { Authorization: authHeader },
        });
        
        if (!res.ok) {
          console.warn(`[chat] REST user search failed with ${res.status}:`, await res.text());
          return [];
        }
        
        const data = await res.json();
        const results = Array.isArray(data) ? data : data.messages || data.results || [];
        return results
          .map((m: any) => m.content || m.text || typeof m === 'string' ? m : null)
          .filter(Boolean)
          .slice(0, limit);
      } catch (restErr: any) {
        console.warn('[chat] REST user search failed:', restErr.message);
        return [];
      }
    } else {
      try {
        const client = getSdkClient();
        console.log('[chat] User-level memory search via SDK not fully implemented, try MCP transport');
        return [];
      } catch (err) {
        console.warn('[chat] SDK user search failed:', err);
        return [];
      }
    }
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
  
  try {
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
        continue;
      }
    }
    return results;
  } catch (err) {
    console.warn('[chat] searchPreviousConversations failed:', err);
    return [];
  }
}

export async function deleteConversation(conversationId: string): Promise<void> {
  if (useMcpTransport()) {
    const restBase = process.env.MEMORY_REST_URL?.trim() || 'https://memory.neo4jlabs.com/v1';
    try {
      const res = await fetch(`${restBase}/short-term/conversations/${conversationId}`, {
        method: 'DELETE',
        headers: { Authorization: getMcpAuthHeader() },
      });
      if (res.status === 404) {
        console.log(`[chat] Conversation ${conversationId} already deleted or never existed (404)`);
        return;
      }
      if (!res.ok) {
        throw new Error(`DELETE ${res.status} ${res.statusText}`);
      }
      console.log(`[chat] Successfully deleted conversation ${conversationId}`);
    } catch (err) {
      console.error(`[chat] Error deleting conversation ${conversationId}:`, err);
      throw err;
    }
  } else {
    try {
      await getSdkClient().shortTerm.deleteConversation(conversationId);
      console.log(`[chat] Successfully deleted conversation ${conversationId}`);
    } catch (err) {
      console.error(`[chat] Error deleting conversation ${conversationId}:`, err);
      throw err;
    }
  }
}
