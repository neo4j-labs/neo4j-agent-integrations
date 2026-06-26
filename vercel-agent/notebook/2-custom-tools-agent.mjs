/**
 * 2-custom-tools-agent.mjs — Custom Cypher Tool + MCP Agent
 *
 * Demonstrates combining the Neo4j MCP server tools with a custom hand-written
 * Cypher-backed tool. Custom tools are defined with tool() + jsonSchema() and
 * merged into the same tools object as MCP tools — the framework routes each
 * call to the correct handler automatically.
 *
 * Prerequisites:
 *   - neo4j-mcp-server running on MCP_PORT (see README for start command)
 *   - Environment variables set (copy .env.example → .env and fill in values)
 *
 * Run:
 *   node 2-custom-tools-agent.mjs
 */

import dotenv from 'dotenv';
dotenv.config();

import { ToolLoopAgent, tool, jsonSchema, stepCountIs } from 'ai';
import { createMCPClient } from '@ai-sdk/mcp';
import neo4j from 'neo4j-driver';
import { getModel } from './providers.mjs';

// ── Configuration ─────────────────────────────────────────────────────────────
const PORT = process.env.MCP_PORT || '8443';
const mcpUrl = process.env.MCP_URL || `http://localhost:${PORT}/mcp`;
const creds = Buffer.from(
  `${process.env.NEO4J_USERNAME}:${process.env.NEO4J_PASSWORD}`
).toString('base64');

// ── MCP tools ─────────────────────────────────────────────────────────────────
// Set MCP_URL to use a hosted remote MCP server; defaults to local.
const mcpClient = await createMCPClient({
  transport: {
    type: 'http',
    url: mcpUrl,
    headers: { Authorization: `Basic ${creds}` },
  },
});
const mcpTools = await mcpClient.tools();
console.log('Connected to Neo4j MCP ✓');

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

const agent = new ToolLoopAgent({
  model,
  instructions: 'You are a helpful assistant with access to a Neo4j graph database containing company data. Use the available tools to answer questions.',
  tools: { ...mcpTools, getInvestments },
  stopWhen: stepCountIs(10),
});

const { text, steps } = await agent.generate({ prompt: 'Which companies did Google invest in?' });

console.log('\nResult:', text);
console.log(`[Completed in ${steps.length} step(s)]`);

await driver.close();
await mcpClient.close();
