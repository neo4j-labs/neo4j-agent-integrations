/**
 * 3-memory-agent.mjs — Neo4j Agent with Custom Graph Memory
 *
 * Demonstrates persistent memory using neo4j-driver directly — no third-party
 * memory packages required. Memory is stored as graph nodes in a writable Neo4j
 * database, making it natively queryable.
 *
 * Memory schema:
 *   (:MemorySession {id})-[:HAS_MESSAGE]->(:MemoryMessage {role, content, timestamp})
 *
 * Pattern:
 *   BEFORE hook — retrieve recent messages and inject into system prompt
 *   AFTER hook  — save interaction as (:MemoryMessage) nodes
 *
 * The two-turn demo shows memory in action:
 *   Turn 1 — establishes research context (Google analysis)
 *   Turn 2 — follow-up; the before-hook injects Turn 1's history so the agent
 *             knows which company was being discussed without being told again.
 *
 * Prerequisites:
 *   - neo4j-mcp-server running on MCP_PORT (see README)
 *   - MEMORY_NEO4J_* env vars pointing to a writable Neo4j database
 *   - All other env vars set (copy .env.example → .env)
 *
 * Run:
 *   node 3-memory-agent.mjs
 */

import { generateText, stepCountIs } from 'ai';
import { experimental_createMCPClient } from '@ai-sdk/mcp';
import neo4j from 'neo4j-driver';
import { getModel } from './providers.mjs';

// ── Configuration ─────────────────────────────────────────────────────────────
const PORT  = process.env.MCP_PORT || '8443';
const creds = Buffer.from(
  `${process.env.NEO4J_USERNAME}:${process.env.NEO4J_PASSWORD}`
).toString('base64');

const MEMORY_URI  = process.env.MEMORY_NEO4J_URI;
const MEMORY_USER = process.env.MEMORY_NEO4J_USERNAME || 'neo4j';
const MEMORY_PASS = process.env.MEMORY_NEO4J_PASSWORD;
const MEMORY_DB   = process.env.MEMORY_NEO4J_DATABASE || 'neo4j';
const SESSION_ID  = `session-${Date.now()}`;

if (!MEMORY_URI) {
  console.error('ERROR: MEMORY_NEO4J_URI is not set. See .env.example for setup.');
  process.exit(1);
}

// ── MCP client (Neo4j knowledge graph tools) ──────────────────────────────────
const mcpClient = await experimental_createMCPClient({
  transport: {
    type:    'http',
    url:     `http://localhost:${PORT}/mcp`,
    headers: { Authorization: `Basic ${creds}` },
  },
});
const mcpTools = await mcpClient.tools();
console.log('Connected to Neo4j MCP ✓');

// ── Memory driver (separate writable Neo4j instance) ─────────────────────────
// Memory is stored as a lightweight graph using neo4j-driver directly —
// no additional packages needed.
//
// Schema:
//   (:MemorySession {id})-[:HAS_MESSAGE]->(:MemoryMessage {role, content, timestamp})
const memDriver = neo4j.driver(MEMORY_URI, neo4j.auth.basic(MEMORY_USER, MEMORY_PASS),
  { disableLosslessIntegers: true });

/** Save a message to the memory graph. */
async function storeMessage(role, content) {
  await memDriver.executeQuery(
    `MERGE (s:MemorySession {id: $sessionId})
     CREATE (m:MemoryMessage {role: $role, content: $content, timestamp: datetime()})
     CREATE (s)-[:HAS_MESSAGE]->(m)`,
    { sessionId: SESSION_ID, role, content },
    { database: MEMORY_DB }
  );
}

/** Retrieve recent conversation messages for context injection. */
async function getRecentMessages(limit = 10) {
  const { records } = await memDriver.executeQuery(
    `MATCH (s:MemorySession {id: $sessionId})-[:HAS_MESSAGE]->(m:MemoryMessage)
     RETURN m.role AS role, m.content AS content
     ORDER BY m.timestamp ASC LIMIT $limit`,
    { sessionId: SESSION_ID, limit },
    { database: MEMORY_DB }
  );
  return records.map(r => `${r.get('role').toUpperCase()}: ${r.get('content')}`);
}

// ── Agent setup ───────────────────────────────────────────────────────────────
const model = await getModel();

const SYSTEM_PROMPT = `You are a helpful graph analyst with access to a Neo4j companies \
knowledge graph. Use the available tools to answer questions accurately.`;

// ── BEFORE hook: inject conversation history into system prompt ───────────────
async function injectMemoryContext(userQuery) {
  const history = await getRecentMessages();
  if (!history.length) return SYSTEM_PROMPT;

  console.log(` ↳ Injecting ${history.length} message(s) from memory.`);
  return `${SYSTEM_PROMPT}\n\n--- CONVERSATION HISTORY ---\n${history.join('\n')}\n----------------------------`;
}

// ── AFTER hook: save interaction to memory graph ──────────────────────────────
async function saveInteraction(userQuery, agentResponse) {
  await storeMessage('user', userQuery);
  await storeMessage('assistant', agentResponse);
  console.log(' [Memory] Interaction saved to Neo4j ✓');
}

// ── Run agent with memory hooks ───────────────────────────────────────────────
async function runWithMemory(query) {
  console.log(`\n[USER]: ${query}`);

  const systemWithContext = await injectMemoryContext(query);

  const { text } = await generateText({
    model,
    system:   systemWithContext,
    prompt:   query,
    tools:    mcpTools,
    stopWhen: stepCountIs(10),
  });

  console.log(`[AGENT]: ${text}`);
  await saveInteraction(query, text);
  return text;
}

// ── Two-turn demo ─────────────────────────────────────────────────────────────
// Turn 1: establish research context
await runWithMemory(
  "I am conducting a competitive analysis of 'Google'. Tell me about their presence in the knowledge graph."
);

// Turn 2: follow-up — conversation history from Turn 1 is injected automatically
await runWithMemory(
  "Based on our conversation, what subsidiaries of the company we discussed appear in the database?"
);

await mcpClient.close();
await memDriver.close();
