
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

/** Runs fn() with a per-request MCP tool recorder active. Returns the result and all tool records. */
export async function runWithMcpTracker<T>(
  fn: () => Promise<T>,
): Promise<{ result: T; mcpTools: McpToolRecord[] }> {
  const records: McpToolRecord[] = [];
  const result = await _mcpRecordStore.run(records, fn);
  return { result, mcpTools: records };
}

// ─── Config ──────────────────────────────────────────────────────────────────

const DEFAULT_SDK_ENDPOINT = 'https://memory.neo4jlabs.com/v1';
const DEFAULT_MCP_URL = 'https://memory.neo4jlabs.com/mcp';
const GOOD_MATCH_THRESHOLD = 0.75;

/** Set MEMORY_TRANSPORT=mcp in your env to use the MCP backend instead of the SDK. */
function useMcpTransport(): boolean {
  return process.env.MEMORY_TRANSPORT?.trim().toLowerCase() === 'mcp';
}

// ─── SDK backend (MEMORY_API_KEY) ────────────────────────────────────────────

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

/** Returns the shared MemoryClient (SDK transport only). Throws if MEMORY_API_KEY is absent. */
export function getMemoryClient(): MemoryClient {
  return getSdkClient();
}

// ─── MCP backend ─────────────────────────────────────────────────────────────
//
// Auth priority:
//   1. Bearer token  — MEMORY_API_KEY        (hosted NAMS MCP server)
//   2. Basic auth    — NEO4J_USERNAME + NEO4J_PASSWORD  (self-hosted MCP server)

function getMcpAuthHeader(): string {
  const apiKey = process.env.MEMORY_API_KEY?.trim();
  if (apiKey) return `Bearer ${apiKey}`;

  const username = process.env.NEO4J_USERNAME?.trim();
  const password = process.env.NEO4J_PASSWORD?.trim();
  if (username && password) {
    return `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;
  }

  throw new Error(
    'MCP transport requires auth. Set MEMORY_API_KEY (Bearer) or NEO4J_USERNAME + NEO4J_PASSWORD (Basic).',
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

/** Returns the MCP tool set for use in streamText / generateText (MCP mode only). */
export async function getMemoryTools() {
  const client = await getMcpClientPromise();
  return client.tools();
}

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

// ─── Public API (auto-selects backend) ───────────────────────────────────────

export async function ensureConversation(
  sessionId: string,
  existingConversationId?: string,
): Promise<string> {
  if (existingConversationId) return existingConversationId;

  try {
    if (useMcpTransport()) {
      const conv = (await callMcpTool('memory_create_conversation', { user_id: sessionId })) as { id: string };
      return conv.id;
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
    return (await callMcpTool('memory_get_context', { conversation_id: conversationId })) as any;
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
    // MCP schema: messages is an array of { role, content } objects
    await callMcpTool('memory_add_messages', {
      conversation_id: conversationId,
      messages: [{ role, content }],
    });
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
      // MCP schema has no threshold param — limit is the only filter available
      const results = (await callMcpTool('memory_search_messages', {
        conversation_id: conversationId,
        query,
        limit,
      })) as Array<{ content: string }>;
      return Array.isArray(results) ? results.map((m) => m.content).filter(Boolean) : [];
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

export async function deleteConversation(conversationId: string): Promise<void> {
  if (useMcpTransport()) {
    // No MCP tool for delete — fall back to REST using the same auth header.
    const restBase = process.env.MEMORY_REST_URL?.trim() || 'https://memory.neo4jlabs.com/v1';
    const res = await fetch(`${restBase}/short-term/conversations/${conversationId}`, {
      method: 'DELETE',
      headers: { Authorization: getMcpAuthHeader() },
    });
    if (!res.ok) throw new Error(`DELETE ${res.status} ${res.statusText}`);
  } else {
    await getSdkClient().shortTerm.deleteConversation(conversationId);
  }
}
