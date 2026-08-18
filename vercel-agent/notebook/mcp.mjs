/**
 * mcp.mjs — Neo4j MCP connection helper
 *
 * Mirrors `lib/neo4j-mcp.ts` in ../vercel_Nams_demo so the scripts and the
 * Next.js demo authenticate against the same servers with the same env vars.
 *
 * Auth precedence:
 *   MCP_BEARER_TOKEN                        → Authorization: Bearer   (OAuth 2.1
 *                                             servers — hosted Aura / NeoCompanion
 *                                             endpoints advertise `WWW-Authenticate: Bearer`)
 *   MCP_NEO4J_USERNAME + MCP_NEO4J_PASSWORD → Authorization: Basic    (self-hosted
 *                                             mcp-neo4j-cypher behind a proxy)
 *
 * The Basic credentials fall back to NEO4J_USERNAME / NEO4J_PASSWORD, which the
 * direct-driver scripts already use, so a single-database .env keeps working.
 *
 * Endpoint: MCP_URL, or http://localhost:${MCP_PORT}/mcp when only MCP_PORT is set.
 */

import { createMCPClient } from '@ai-sdk/mcp';

/**
 * @returns {{ url: string, headers: Record<string,string>, authScheme: 'bearer' | 'basic' } | null}
 */
export function getMcpConfig() {
  const port = process.env.MCP_PORT?.trim();
  const url  = process.env.MCP_URL?.trim() || (port ? `http://localhost:${port}/mcp` : '');
  if (!url) return null;

  const token = process.env.MCP_BEARER_TOKEN?.trim();
  if (token) {
    return { url, headers: { Authorization: `Bearer ${token}` }, authScheme: 'bearer' };
  }

  const username = (process.env.MCP_NEO4J_USERNAME || process.env.NEO4J_USERNAME)?.trim();
  const password = (process.env.MCP_NEO4J_PASSWORD || process.env.NEO4J_PASSWORD)?.trim();
  if (!username || !password) return null;

  const creds = Buffer.from(`${username}:${password}`).toString('base64');
  return { url, headers: { Authorization: `Basic ${creds}` }, authScheme: 'basic' };
}

/** True when enough env vars are set to attempt a connection. */
export function isMcpConfigured() {
  return getMcpConfig() !== null;
}

/**
 * Connects to the Neo4j MCP server and returns its tools.
 *
 * @returns {Promise<{ tools: Record<string, unknown>, close: () => Promise<void> } | null>}
 *          null when MCP is not configured.
 */
export async function getMcpTools() {
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
  console.log(`[neo4j-mcp] Connected (${config.authScheme} auth) — tools: ${Object.keys(tools).join(', ')}`);

  return { tools, close: () => client.close() };
}

/**
 * The McpConfig shape expected by `createNams().toolsWithMcp()`.
 * Use this in tools mode; use getMcpTools() everywhere else.
 *
 * @returns {{ url: string, headers: Record<string,string> } | undefined}
 */
export function getNamsMcpConfig() {
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
 *
 * @param {unknown} err
 * @returns {Promise<string>}
 */
export async function explainMcpError(err) {
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
