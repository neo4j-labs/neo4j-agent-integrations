/**
 * 1-mcp-agent.mjs — Neo4j MCP Agent
 *
 * Demonstrates connecting to the Neo4j MCP server and running a multi-step
 * agentic query. The agent automatically decides which MCP tools to call
 * (get-schema, read-cypher, etc.) to answer the user's question.
 *
 * Auth is handled by mcp.mjs — bearer token for hosted OAuth 2.1 servers,
 * Basic auth for a self-hosted mcp-neo4j-cypher. Same helper shape as
 * lib/neo4j-mcp.ts in ../vercel_Nams_demo.
 *
 * Prerequisites:
 *   - MCP_URL (hosted) or MCP_PORT (local neo4j-mcp-server), plus MCP auth vars
 *   - Environment variables set (copy .env.example → .env and fill in values)
 *
 * Run:
 *   node 1-mcp-agent.mjs
 */

import dotenv from 'dotenv';
dotenv.config();

import { generateText, stepCountIs } from 'ai';
import { getModel } from './providers.mjs';
import { getMcpTools, isMcpConfigured, explainMcpError } from './mcp.mjs';
import { GRAPH_SYSTEM_PROMPT } from './prompts.mjs';

// ── Connect to Neo4j MCP server ───────────────────────────────────────────────
if (!isMcpConfigured()) {
  console.error(
    'ERROR: MCP is not configured. Set MCP_URL (or MCP_PORT) plus either\n' +
    '       MCP_BEARER_TOKEN, or MCP_NEO4J_USERNAME + MCP_NEO4J_PASSWORD.'
  );
  process.exit(1);
}

const mcp = await getMcpTools().catch(async (err) => {
  console.error('ERROR: Neo4j MCP connection failed:', await explainMcpError(err));
  process.exit(1);
});

// ── Agent helper ──────────────────────────────────────────────────────────────
function createAgent({ model, name, instruction, tools }) {
  return { model, name, instruction, tools };
}

async function askGraph(agent, query) {
  console.log(`Query: ${query}`);
  const { text, steps } = await generateText({
    model:    agent.model,
    system:   agent.instruction,
    prompt:   query,
    tools:    agent.tools,
    stopWhen: stepCountIs(10),  // AI SDK v6: replaces maxSteps
  });
  console.log(`\nResult: ${text}`);
  console.log(`[Completed in ${steps.length} step(s)]\n`);
  return text;
}

// ── Build the agent ───────────────────────────────────────────────────────────
const model = await getModel();

const mcpAgent = createAgent({
  model,
  name:        'neo4j_explorer',
  instruction: GRAPH_SYSTEM_PROMPT,
  tools:       mcp.tools,
});

console.log(`Agent:  ${mcpAgent.name}`);
console.log(`Tools:  ${Object.keys(mcpAgent.tools).join(', ')}\n`);

// ── Run example query ─────────────────────────────────────────────────────────
await askGraph(mcpAgent, 'How many organizations are in the database?');

await mcp.close();
