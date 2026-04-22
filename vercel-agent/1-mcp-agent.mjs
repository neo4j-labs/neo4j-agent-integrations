/**
 * 1-mcp-agent.mjs — Neo4j MCP Agent
 *
 * Demonstrates connecting to the Neo4j MCP server and running a multi-step
 * agentic query. The agent automatically decides which MCP tools to call
 * (get-schema, read-cypher, etc.) to answer the user's question.
 *
 * Prerequisites:
 *   - neo4j-mcp-server running on MCP_PORT (see README for start command)
 *   - Environment variables set (copy .env.example → .env and fill in values)
 *
 * Run:
 *   node 1-mcp-agent.mjs
 */

import { generateText, stepCountIs } from 'ai';
import { experimental_createMCPClient } from '@ai-sdk/mcp';
import { getModel } from './providers.mjs';

// ── Configuration ─────────────────────────────────────────────────────────────
const PORT  = process.env.MCP_PORT || '8443';
const creds = Buffer.from(
  `${process.env.NEO4J_USERNAME}:${process.env.NEO4J_PASSWORD}`
).toString('base64');

// ── Connect to Neo4j MCP server ───────────────────────────────────────────────
// Credentials are passed per-request via Basic Auth (not as env vars on the server process).
const mcpClient = await experimental_createMCPClient({
  transport: {
    type:    'http',
    url:     `http://localhost:${PORT}/mcp`,
    headers: { Authorization: `Basic ${creds}` },
  },
});

const mcpTools = await mcpClient.tools();
console.log('Connected to Neo4j MCP ✓');
console.log('Available tools:', Object.keys(mcpTools).join(', '), '\n');

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
  instruction: `You are a graph database assistant. Your job is to answer user questions by querying Neo4j.
Always run 'get-schema' first if you are unfamiliar with the graph structure.
Use Cypher queries to retrieve data.
After running a query, always provide a clear text summary of the results.
If the data is not found, state that clearly.`,
  tools: mcpTools,
});

console.log(`Agent:  ${mcpAgent.name}`);
console.log(`Model:  ${process.env.AI_PROVIDER || 'openai'} / ${process.env.AI_MODEL || 'gpt-4o'}`);
console.log(`Tools:  ${Object.keys(mcpAgent.tools).join(', ')}\n`);

// ── Run example query ─────────────────────────────────────────────────────────
await askGraph(mcpAgent, 'How many organizations are in the database?');

await mcpClient.close();
