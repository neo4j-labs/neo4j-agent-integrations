// Connects to a Neo4j MCP server.
// Auth: MCP_BEARER_TOKEN, or MCP_NEO4J_USERNAME + MCP_NEO4J_PASSWORD. The token wins if both are set.

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

/** The same server, in the shape `createNams().toolsWithMcp()` takes. */
export function getNamsMcpConfig(): McpConfig | undefined {
  const config = getMcpConfig();
  if (!config) return undefined;
  return { url: config.url, headers: config.headers };
}

/** Makes an MCP error readable. On a 401 it asks the server which auth it wants. */
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

/** True when a URL and one auth pair are set. */
export function isMcpConfigured(): boolean {
  const hasUrl = Boolean(process.env.MCP_URL?.trim() || process.env.MCP_PORT?.trim());
  const hasAuth = Boolean(
    process.env.MCP_BEARER_TOKEN?.trim() ||
    (process.env.MCP_NEO4J_USERNAME?.trim() && process.env.MCP_NEO4J_PASSWORD?.trim()),
  );
  return hasUrl && hasAuth;
}

// A query with no LIMIT can return megabytes, and a heavy one can run for minutes.
// Either one would fail the whole turn, so tool results are cut short in both cases.
const MAX_TOOL_OUTPUT_CHARS = 50_000;
const TOOL_TIMEOUT_MS = 30_000;

function truncateText(text: string): string {
  if (text.length <= MAX_TOOL_OUTPUT_CHARS) return text;
  return (
    text.slice(0, MAX_TOOL_OUTPUT_CHARS) +
    `\n\n[…truncated: result was ${text.length.toLocaleString()} characters, showing the first ` +
    `${MAX_TOOL_OUTPUT_CHARS.toLocaleString()}. Add a LIMIT clause to your Cypher query to see the ` +
    `rest, or ask a more specific question.]`
  );
}

function capOutput(output: unknown): unknown {
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

const timedOut = (name: string) => ({
  isError: true,
  content: [{
    type: 'text',
    text: `${name} took longer than ${TOOL_TIMEOUT_MS / 1000}s and was stopped. ` +
      'Try a smaller query: fewer OPTIONAL MATCHes, count() instead of rows, and a LIMIT.',
  }],
});

/** Wraps each tool so a slow call stops after 30s and a huge result is cut short. */
export function guardTools<T extends Record<string, unknown>>(tools: T): T {
  const guarded: Record<string, unknown> = {};
  for (const [name, t] of Object.entries(tools)) {
    const original = (t as { execute?: (input: unknown, opts?: any) => unknown })?.execute;
    if (typeof original !== 'function') {
      guarded[name] = t;
      continue;
    }
    guarded[name] = {
      ...(t as object),
      execute: async (input: unknown, opts: any = {}) => {
        let timer: ReturnType<typeof setTimeout> | undefined;
        const timeout = new Promise(resolve => {
          timer = setTimeout(() => resolve(timedOut(name)), TOOL_TIMEOUT_MS);
        });
        try {
          return capOutput(await Promise.race([original(input, opts), timeout]));
        } finally {
          clearTimeout(timer);
        }
      },
    };
  }
  return guarded as T;
}
