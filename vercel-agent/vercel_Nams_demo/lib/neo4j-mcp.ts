/**
 * neo4j-mcp.ts — Neo4j MCP client helper for just the demo.
 *
 * Auth: set MCP_BEARER_TOKEN for servers behind OAuth 2.1 (hosted Aura /
 * NeoCompanion endpoints advertise `WWW-Authenticate: Bearer`), or
 * MCP_NEO4J_USERNAME + MCP_NEO4J_PASSWORD for a self-hosted mcp-neo4j-cypher
 * behind Basic auth. Bearer wins when both are present.
 */

import { createMCPClient } from '@ai-sdk/mcp';
import type { McpConfig } from '@neo4j-labs/nams-ai-provider';

export interface Neo4jMcpConfig {
  url: string;
  headers: Record<string, string>;
  authScheme: 'bearer' | 'basic';
}

function getMcpConfig(): Neo4jMcpConfig | null {
  const port = process.env.MCP_PORT?.trim();
  const url  = process.env.MCP_URL?.trim() || (port ? `http://localhost:${port}/mcp` : '');
  if (!url) return null;

  const token = process.env.MCP_BEARER_TOKEN?.trim();
  if (token) {
    return { url, headers: { Authorization: `Bearer ${token}` }, authScheme: 'bearer' };
  }

  const username = process.env.MCP_NEO4J_USERNAME?.trim();
  const password = process.env.MCP_NEO4J_PASSWORD?.trim();
  if (!username || !password) return null;

  const creds = Buffer.from(`${username}:${password}`).toString('base64');
  return { url, headers: { Authorization: `Basic ${creds}` }, authScheme: 'basic' };
}

export async function getNeo4jMcpTools(): Promise<{
  tools: Record<string, unknown>;
  close: () => Promise<void>;
} | null> {
  const config = getMcpConfig();
  if (!config) return null;

  const client = await createMCPClient({
    transport: {
      type:    'http',
      url:     config.url,
      headers: config.headers,
    },
  });

  const tools = await client.tools();
  console.log(`[neo4j-mcp] Connected — tools: ${Object.keys(tools).join(', ')}`);

  return {
    tools,
    close: () => client.close(),
  };
}

/**
 * Returns the McpConfig format expected by createNams().toolsWithMcp().
 * Use this in tools mode; for provider mode use getNeo4jMcpTools() directly.
 */
export function getNamsMcpConfig(): McpConfig | undefined {
  const config = getMcpConfig();
  if (!config) return undefined;
  return { url: config.url, headers: config.headers };
}

/**
 * Turns an opaque MCP transport error into something actionable.
 *
 * `@ai-sdk/mcp` surfaces the failure as a bare message string ("MCP HTTP
 * Transport Error: POSTing to endpoint (HTTP 401):") with no status or headers
 * attached, so on a 401 we re-probe the endpoint to read its `WWW-Authenticate`
 * challenge and report the scheme mismatch outright.
 */
export async function explainMcpError(err: unknown): Promise<string> {
  const message = err instanceof Error ? err.message : String(err);
  const config = getMcpConfig();
  if (!config || !/\b401\b/.test(message)) return message;

  const challenge = await fetch(config.url, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json, text/event-stream' },
    body:    '{}',
  })
    .then(res => res.headers.get('www-authenticate'))
    .catch(() => null);

  if (!challenge) return message;

  const wanted = challenge.split(/[\s,]/)[0]?.toLowerCase();
  return wanted && wanted !== config.authScheme
    ? `${message} server requires ${wanted} auth, but the MCP_* env vars produced ${config.authScheme}. ` +
      `Challenge: ${challenge}`
    : `${message} ${challenge}`;
}

/** Returns true if enough MCP env vars are set to attempt a connection. */
export function isMcpConfigured(): boolean {
  const hasUrl = Boolean(process.env.MCP_URL?.trim() || process.env.MCP_PORT?.trim());
  const hasAuth = Boolean(
    process.env.MCP_BEARER_TOKEN?.trim() ||
    (process.env.MCP_NEO4J_USERNAME?.trim() && process.env.MCP_NEO4J_PASSWORD?.trim()),
  );
  return hasUrl && hasAuth;
}

// An unbounded Cypher query (e.g. `MATCH (n) RETURN n` with no LIMIT) can
// return megabytes of JSON from read-cypher. Fed straight back as a tool
// result, that alone can exceed the model provider's per-field request-body
// limit (e.g. OpenAI's 10 MiB `input[].output[].text` cap), which fails the
// *entire* turn with an opaque 400 — surfacing to the user as a generic
// "I was not able to produce an answer" with no indication why. Cap tool
// output size here so a too-broad query degrades to a truncated result the
// model can react to (and be nudged to add a LIMIT) instead of a hard failure.
const MAX_TOOL_OUTPUT_CHARS = 50_000;

function truncateText(text: string): string {
  if (text.length <= MAX_TOOL_OUTPUT_CHARS) return text;
  return (
    text.slice(0, MAX_TOOL_OUTPUT_CHARS) +
    `\n\n[…truncated: result was ${text.length.toLocaleString()} characters, showing the first ` +
    `${MAX_TOOL_OUTPUT_CHARS.toLocaleString()}. Add a LIMIT clause to your Cypher query to see the ` +
    `rest, or ask a more specific question.]`
  );
}

/** Shrinks any oversized text found in an MCP tool result to a safe size. */
function capMcpOutput(output: unknown): unknown {
  if (output && typeof output === 'object' && Array.isArray((output as { content?: unknown }).content)) {
    const withContent = output as { content: Array<{ type?: string; text?: string }> };
    return {
      ...withContent,
      content: withContent.content.map(item =>
        item?.type === 'text' && typeof item.text === 'string'
          ? { ...item, text: truncateText(item.text) }
          : item,
      ),
    };
  }
  if (typeof output === 'string') return truncateText(output);
  return output;
}

/**
 * Wraps every tool's `execute` so oversized results get capped before they
 * reach the model. Safe to apply to any ToolSet (MCP tools, NAMS memory
 * tools, or a merge of both) — tools without an `execute` pass through
 * unchanged.
 */
export function capToolOutputs<T extends Record<string, unknown>>(tools: T): T {
  const capped: Record<string, unknown> = {};
  for (const [name, t] of Object.entries(tools)) {
    const original = (t as { execute?: (...args: unknown[]) => unknown })?.execute;
    capped[name] = typeof original === 'function'
      ? { ...(t as object), execute: async (...args: unknown[]) => capMcpOutput(await original(...args)) }
      : t;
  }
  return capped as T;
}
