/**
 * neo4j-mcp.ts — Neo4j MCP client helper for the Vercel AI SDK.
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
