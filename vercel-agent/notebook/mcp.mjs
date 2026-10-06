// Connects to a Neo4j MCP server. Same env vars as ../vercel_Nams_demo/lib/neo4j-mcp.ts.
// Auth: MCP_BEARER_TOKEN, or MCP_NEO4J_USERNAME + MCP_NEO4J_PASSWORD
// (falling back to NEO4J_USERNAME / NEO4J_PASSWORD). The token wins if both are set.
// URL: MCP_URL, or http://localhost:${MCP_PORT}/mcp.

import { createMCPClient } from '@ai-sdk/mcp';

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

/** Connects and returns the server's tools, or null when MCP is not configured. */
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

  return { tools: guardTools(tools), close: () => client.close() };
}

/** The same server, in the shape `createNams().toolsWithMcp()` takes. */
export function getNamsMcpConfig() {
  const config = getMcpConfig();
  if (!config) return undefined;
  return { url: config.url, headers: config.headers };
}

/** Makes an MCP error readable. On a 401 it asks the server which auth it wants. */
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

// A query with no LIMIT can return megabytes, and a heavy one can run for minutes.
// Either one would fail the whole turn, so tool results are cut short in both cases.
const MAX_TOOL_OUTPUT_CHARS = 50_000;
const TOOL_TIMEOUT_MS = 30_000;

function truncateText(text) {
  if (text.length <= MAX_TOOL_OUTPUT_CHARS) return text;
  return text.slice(0, MAX_TOOL_OUTPUT_CHARS) +
    `\n\n[…truncated: result was ${text.length.toLocaleString()} characters. ` +
    'Add a LIMIT clause to your Cypher query, or ask a more specific question.]';
}

function capOutput(output) {
  if (Array.isArray(output?.content)) {
    return {
      ...output,
      content: output.content.map(item =>
        item?.type === 'text' && typeof item.text === 'string' ? { ...item, text: truncateText(item.text) } : item),
    };
  }
  return typeof output === 'string' ? truncateText(output) : output;
}

const timedOut = (name) => ({
  isError: true,
  content: [{
    type: 'text',
    text: `${name} took longer than ${TOOL_TIMEOUT_MS / 1000}s and was stopped. ` +
      'Try a smaller query: fewer OPTIONAL MATCHes, count() instead of rows, and a LIMIT.',
  }],
});

/** Wraps each tool so a slow call stops after 30s and a huge result is cut short. */
export function guardTools(tools) {
  return Object.fromEntries(Object.entries(tools).map(([name, t]) => {
    if (typeof t?.execute !== 'function') return [name, t];
    return [name, {
      ...t,
      execute: async (input, opts = {}) => {
        let timer;
        const timeout = new Promise(resolve => { timer = setTimeout(() => resolve(timedOut(name)), TOOL_TIMEOUT_MS); });
        try {
          return capOutput(await Promise.race([t.execute(input, opts), timeout]));
        } finally {
          clearTimeout(timer);
        }
      },
    }];
  }));
}
