
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
const GOOD_MATCH_THRESHOLD = 0.5;

// Logging

function preview(text: string, maxLen = 80): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  return clean.length > maxLen ? clean.slice(0, maxLen) + '…' : clean;
}

function tag(label: string): string {
  return `[Memory:${label}]`;
}

// SDK client

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
    console.log(`${tag('Init')} Connected to ${endpoint}${workspaceId ? ` (workspace: ${workspaceId})` : ''}`);
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

// Conversation lifecycle

export async function ensureConversation(
  sessionId: string,
  existingConversationId?: string,
): Promise<string> {
  if (existingConversationId) {
    console.log(`${tag('Conversation')} Reusing existing conversation: ${existingConversationId}`);
    return existingConversationId;
  }
  try {
    console.log(`${tag('Conversation')} Creating new conversation for user/session: ${sessionId}`);
    const t0 = Date.now();
    const conv = await getSdkClient().shortTerm.createConversation({ userId: sessionId });
    console.log(`${tag('Conversation')} Created → id: ${conv.id} (${Date.now() - t0}ms)`);
    return conv.id;
  } catch (err) {
    console.error(`${tag('Conversation')} Failed to create conversation for session ${sessionId}:`, err);
    throw err;
  }
}

// Context retrieval

export async function getConversationContext(conversationId: string): Promise<{
  recentMessages: Array<{ role: string; content: string }>;
  reflections: Array<{ content: string }>;
  observations: Array<{ content: string }>;
}> {
  console.log(`${tag('Context')} Fetching context for conversation: ${conversationId}`);
  const t0 = Date.now();
  const ctx = await getSdkClient().shortTerm.getContext(conversationId) as any;
  const msgCount = ctx.recentMessages?.length ?? 0;
  const refCount = ctx.reflections?.length ?? 0;
  const obsCount = ctx.observations?.length ?? 0;
  console.log(
    `${tag('Context')} Retrieved in ${Date.now() - t0}ms → ` +
    `${msgCount} recent message(s), ${refCount} reflection(s), ${obsCount} observation(s)`,
  );
  if (msgCount > 0) {
    (ctx.recentMessages as Array<{ role: string; content: string }>).forEach((m, i) => {
      console.log(`${tag('Context')}   [${i + 1}] ${m.role}: "${preview(m.content)}"`);
    });
  }
  if (refCount > 0) {
    (ctx.reflections as Array<{ content: string }>).forEach((r, i) => {
      console.log(`${tag('Context')}   [reflection ${i + 1}] "${preview(r.content)}"`);
    });
  }
  if (obsCount > 0) {
    (ctx.observations as Array<{ content: string }>).forEach((o, i) => {
      console.log(`${tag('Context')}   [observation ${i + 1}] "${preview(o.content)}"`);
    });
  }
  return ctx;
}

// Message persistence

export async function addMessage(
  conversationId: string,
  role: 'user' | 'assistant',
  content: string,
): Promise<void> {
  console.log(`${tag('Store')} Persisting ${role} message to conversation ${conversationId}: "${preview(content)}"`);
  const t0 = Date.now();
  await getSdkClient().shortTerm.addMessage(conversationId, role, content);
  console.log(`${tag('Store')} ✓ ${role} message stored (${Date.now() - t0}ms)`);
}

//Semantic search

export async function searchMemoryContext(
  conversationId: string,
  query: string,
  limit = 5,
): Promise<string[]> {
  if (!query.trim()) return [];
  console.log(
    `${tag('Search')} Searching current conversation (${conversationId}) for: "${preview(query)}" ` +
    `[threshold: ${GOOD_MATCH_THRESHOLD}, limit: ${limit}]`,
  );
  const t0 = Date.now();
  try {
    const results = await getSdkClient().shortTerm.searchMessages(query, {
      sessionId: conversationId,
      limit,
      threshold: GOOD_MATCH_THRESHOLD,
    });
    const hits = results.map((m) => m.content).filter(Boolean);
    console.log(`${tag('Search')} Current conversation → ${hits.length} hit(s) (${Date.now() - t0}ms)`);
    hits.forEach((h, i) => console.log(`${tag('Search')}   [${i + 1}] "${preview(h)}"`));
    return hits;
  } catch (err) {
    console.warn(`${tag('Search')} searchMessages failed (${Date.now() - t0}ms):`, err);
    return [];
  }
}

export async function searchUserMemoryContext(
  userId: string,
  query: string,
  limit = 3,
): Promise<string[]> {
  if (!query.trim()) return [];
  console.log(`${tag('UserSearch')} Searching all conversations for user "${userId}": "${preview(query)}"`);
  const t0 = Date.now();
  try {
    const conversations = await getSdkClient().shortTerm.listConversations({ userId, limit: 20 });
    console.log(`${tag('UserSearch')} Found ${conversations.length} conversation(s) for user`);
    const seen = new Set<string>();
    const results: string[] = [];
    for (const conv of conversations) {
      if (results.length >= limit) break;
      try {
        const matches = await getSdkClient().shortTerm.searchMessages(query, {
          sessionId: conv.id,
          limit: 2,
          threshold: GOOD_MATCH_THRESHOLD,
        });
        const newHits = matches
          .map((m) => m.content)
          .filter((c): c is string => !!c && !seen.has(c));
        for (const h of newHits) {
          if (results.length >= limit) break;
          results.push(h);
          seen.add(h);
          console.log(`${tag('UserSearch')}   hit from conv ${conv.id}: "${preview(h)}"`);
        }
      } catch (err: unknown) {
        console.warn(`${tag('UserSearch')} Search failed for conversation ${conv.id}:`, err);
      }
    }
    console.log(`${tag('UserSearch')} Total user-level hits: ${results.length} (${Date.now() - t0}ms)`);
    return results;
  } catch (err: unknown) {
    console.warn(`${tag('UserSearch')} Failed to list conversations for user ${userId} (${Date.now() - t0}ms):`, err);
    return [];
  }
}

export async function searchPreviousConversations(
  conversationIds: string[],
  query: string,
  limit = 3,
): Promise<string[]> {
  if (!query.trim() || !conversationIds.length) return [];
  console.log(
    `${tag('PrevSearch')} Searching ${conversationIds.length} previous conversation(s) for: "${preview(query)}"`,
  );
  const t0 = Date.now();
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
      console.warn('%s Failed to search conversation %s:', tag('PrevSearch'), convId, err);
    }
  }
  console.log(`${tag('PrevSearch')} Total previous-conversation hits: ${results.length} (${Date.now() - t0}ms)`);
  return results;
}

export async function getConversationReasoning(conversationId: string) {
  console.log(`${tag('Reasoning')} Fetching trace for conversation: ${conversationId}`);
  const t0 = Date.now();
  const trace = await getSdkClient().reasoning.getTraceByConversation(conversationId);
  console.log(`${tag('Reasoning')} Retrieved in ${Date.now() - t0}ms → ${(trace as any).steps?.length ?? 0} step(s)`);
  return trace;
}

export async function recordConversationReasoningSteps(
  conversationId: string,
  steps: Array<{
    text: string;
    toolCalls: Array<{ toolName: string; input: unknown }>;
    toolResults: Array<{ toolCallId: string; toolName: string; output: unknown }>;
  }>,
): Promise<void> {
  console.log(`${tag('Reasoning')} Recording ${steps.length} step(s) for conversation: ${conversationId}`);

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const hasTools = step.toolCalls.length > 0;
    const stepLabel = `step ${i + 1}/${steps.length}`;

    console.log(
      `${tag('Reasoning')} [${stepLabel}] hasTools=${hasTools} | toolCalls=${step.toolCalls.length} | toolResults=${step.toolResults.length} | textLen=${step.text.length}`,
    );

    if (hasTools) {
      console.log(
        `${tag('Reasoning')} [${stepLabel}] tools: ${step.toolCalls.map((t) => t.toolName).join(', ')}`,
      );
      step.toolCalls.forEach((t) => {
        console.log(`${tag('Reasoning')} [${stepLabel}]   call  → ${t.toolName}: ${JSON.stringify(t.input ?? {}).slice(0, 200)}`);
      });
      step.toolResults.forEach((r) => {
        const out = typeof r.output === 'string' ? r.output : JSON.stringify(r.output);
        console.log(`${tag('Reasoning')} [${stepLabel}]   result← ${r.toolName}: "${preview(out)}"`);
      });

      const actionTaken = step.toolCalls
        .map((t) => `${t.toolName}(${JSON.stringify(t.input ?? {}).slice(0, 200)})`)
        .join('; ');
      const result = step.toolResults
        .map((r) => {
          const out = typeof r.output === 'string' ? r.output : JSON.stringify(r.output);
          return `${r.toolName}: ${out.slice(0, 300)}`;
        })
        .join(' | ')
        .slice(0, 800) || undefined;

      const t0 = Date.now();
      const recorded = await getSdkClient().reasoning.recordStep({
        conversationId,
        reasoning: `Using tools: ${step.toolCalls.map((t) => t.toolName).join(', ')}`,
        actionTaken,
        result,
      }).catch((err) => {
        console.warn(`${tag('Reasoning')} [${stepLabel}] ✗ Failed to record tool step:`, err);
        return null;
      });
      if (recorded) {
        const stepId = (recorded as any).id as string;
        console.log(`${tag('Reasoning')} [${stepLabel}] ✓ Tool step recorded → id: ${stepId} (${Date.now() - t0}ms)`);
        for (const call of step.toolCalls) {
          const resultRecord = step.toolResults.find((r) => r.toolName === call.toolName);
          const rawOut = resultRecord?.output;
          const resultStr = rawOut == null ? undefined : typeof rawOut === 'string' ? rawOut : JSON.stringify(rawOut);
          await getSdkClient().reasoning.recordToolCall(
            stepId,
            call.toolName,
            (call.input ?? {}) as Record<string, unknown>,
            { result: resultStr, status: 'success' },
          ).catch((err) => {
            console.warn(`${tag('Reasoning')} [${stepLabel}] ✗ Failed to record tool call ${call.toolName}:`, err);
          });
        }
      }
    } else if (step.text) {
      console.log(`${tag('Reasoning')} [${stepLabel}] text step: "${preview(step.text)}"`);

      const t0 = Date.now();
      const recorded = await getSdkClient().reasoning.recordStep({
        conversationId,
        reasoning: step.text.slice(0, 1000),
        actionTaken: 'generate_response',
      }).catch((err) => {
        console.warn(`${tag('Reasoning')} [${stepLabel}] ✗ Failed to record text step:`, err);
        return null;
      });
      if (recorded) {
        console.log(`${tag('Reasoning')} [${stepLabel}] ✓ Text step recorded → id: ${(recorded as any).id} (${Date.now() - t0}ms)`);
      }
    } else {
      console.log(`${tag('Reasoning')} [${stepLabel}] skipped (no tools and no text)`);
    }
  }

  console.log(`${tag('Reasoning')} ✓ Finished recording steps for conversation: ${conversationId}`);
}

//Conversation deletion

export async function deleteConversation(conversationId: string): Promise<void> {
  console.log(`${tag('Delete')} Deleting conversation: ${conversationId}`);
  try {
    await getSdkClient().shortTerm.deleteConversation(conversationId);
    console.log(`${tag('Delete')} ✓ Conversation ${conversationId} deleted`);
  } catch (err) {
    console.error(`${tag('Delete')} Failed to delete conversation %s:`, conversationId, err);
    throw err;
  }
}
