/**
 * neo4j-mcp.ts — Neo4j MCP client helper for the Vercel AI SDK.
 */

import { createMCPClient } from '@ai-sdk/mcp';

export interface Neo4jMcpConfig {
  url: string;
  username: string;
  password: string;
}

function getMcpConfig(): Neo4jMcpConfig | null {
  const username = process.env.MCP_NEO4J_USERNAME?.trim();
  const password = process.env.MCP_NEO4J_PASSWORD?.trim();
  if (!username || !password) return null;
  const port = process.env.MCP_PORT?.trim();
  const url  = process.env.MCP_URL?.trim() || (port ? `http://localhost:${port}/mcp` : '');
  if (!url) return null;

  return { url, username, password };
}

export async function getNeo4jMcpTools(): Promise<{
  tools: Record<string, unknown>;
  close: () => Promise<void>;
} | null> {
  const config = getMcpConfig();
  if (!config) return null;

  const creds = Buffer.from(`${config.username}:${config.password}`).toString('base64');

  const client = await createMCPClient({
    transport: {
      type:    'http',
      url:     config.url,
      headers: { Authorization: `Basic ${creds}` },
    },
  });

  const tools = await client.tools();
  console.log(`[neo4j-mcp] Connected — tools: ${Object.keys(tools).join(', ')}`);

  return {
    tools,
    close: () => client.close(),
  };
}

/** Returns true if enough MCP env vars are set to attempt a connection. */
export function isMcpConfigured(): boolean {
  const hasUrl  = Boolean(process.env.MCP_URL?.trim() || process.env.MCP_PORT?.trim());
  const hasCreds = Boolean(
    process.env.MCP_NEO4J_USERNAME?.trim() &&
    process.env.MCP_NEO4J_PASSWORD?.trim(),
  );
  return hasUrl && hasCreds;
}
