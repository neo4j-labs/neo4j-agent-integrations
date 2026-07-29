/**
 * 2-custom-tools-agent.mjs — Custom Cypher Tool + MCP Agent
 *
 * Demonstrates combining the Neo4j MCP server tools with a custom hand-written
 * Cypher-backed tool. Custom tools are defined with tool() + jsonSchema() and
 * merged into the same tools object as MCP tools — the framework routes each
 * call to the correct handler automatically.
 *
 * Prerequisites:
 *   - MCP_URL (hosted) or MCP_PORT (local neo4j-mcp-server), plus MCP auth vars
 *   - Environment variables set (copy .env.example → .env and fill in values)
 *
 * Run:
 *   node 2-custom-tools-agent.mjs
 */

import dotenv from 'dotenv';
dotenv.config();

import { generateText, tool, jsonSchema, stepCountIs } from 'ai';
import neo4j from 'neo4j-driver';
import { getModel } from './providers.mjs';
import { getMcpTools, isMcpConfigured, explainMcpError } from './mcp.mjs';

// ── MCP tools ─────────────────────────────────────────────────────────────────
// Bearer or Basic auth, resolved from the MCP_* env vars by mcp.mjs.
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

// ── Direct Neo4j driver (for custom tools) ────────────────────────────────────
const driver = neo4j.driver(
  process.env.NEO4J_URI,
  neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD),
  { disableLosslessIntegers: true }
);

// ── Custom tool: investment relationships ─────────────────────────────────────
// Uses tool() + inputSchema: jsonSchema({}) — no Zod required in AI SDK v6.
const getInvestments = tool({
  description: 'Returns the investments made by a company. Returns a list of investment ids, names and types.',
  inputSchema: jsonSchema({
    type: 'object',
    properties: {
      company: { type: 'string', description: 'Company or organization name' },
    },
    required: ['company'],
  }),
  execute: async ({ company }) => {
    const { records } = await driver.executeQuery(
      `MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
       WHERE o.name = $company
       RETURN i.id AS id, i.name AS name, head(labels(i)) AS type`,
      { company },
      { database: process.env.NEO4J_DATABASE }
    );
    return records.map(r => r.toObject());
  },
});

// ── Build agent with MCP tools + custom tool ──────────────────────────────────
const model = await getModel();

const { text, steps } = await generateText({
  model,
  system:   'You are a helpful assistant with access to a Neo4j graph database containing company data. Use the available tools to answer questions.',
  prompt:   'Which companies did Google invest in?',
  tools:    { ...mcp.tools, getInvestments },  // custom tool merged with MCP tools
  stopWhen: stepCountIs(10),
});

console.log('\nResult:', text);
console.log(`[Completed in ${steps.length} step(s)]`);

await driver.close();
await mcp.close();
