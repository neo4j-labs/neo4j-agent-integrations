/**
 * 3-memory-agent.mjs — Neo4j Agent with @neo4j-labs/agent-memory (low-level client)
 *
 * The hand-rolled version of memory: you own the before/after hooks. For the
 * packaged equivalent — the same memory wired in as a provider, middleware, or
 * a pair of tools — see 4-nams-provider-agent.mjs, which is what the Next.js
 * demo in ../vercel_Nams_demo runs.
 *
 * Demonstrates persistent memory using the official Neo4j Agent Memory Service
 * (NAMS) via the @neo4j-labs/agent-memory TypeScript client. Memory is split into:
 *
 *   Short-term  — conversation messages, reflections, observations (scoped to a
 *                 conversation session via shortTerm.createConversation)
 *   Long-term   — named entities (facts, topics, research findings) stored
 *                 persistently and searchable via longTerm.searchEntities
 *
 * Pattern:
 *   BEFORE query — retrieve conversation context + relevant long-term entities,
 *                  inject into system prompt
 *   AFTER  query — save user + assistant messages to short-term memory; save
 *                  key findings as long-term entities
 *
 * The two-turn demo shows memory in action:
 *   Turn 1 — establishes research context (Google analysis)
 *   Turn 2 — follow-up; injected context lets the agent know which company was
 *             discussed without being told again.
 *
 * Prerequisites:
 *   - MCP_URL (hosted) or MCP_PORT (local neo4j-mcp-server), plus MCP auth vars
 *   - MEMORY_API_KEY set (get a free key at memory.neo4jlabs.com)
 *   - All other env vars set (copy .env.example → .env)
 *
 * Run:
 *   node 3-memory-agent.mjs
 */

import dotenv from 'dotenv';
dotenv.config();

import { generateText, stepCountIs } from 'ai';
import { MemoryClient } from '@neo4j-labs/agent-memory';
import { getModel } from './providers.mjs';
import { getMcpTools, isMcpConfigured, explainMcpError } from './mcp.mjs';

// ── Configuration ─────────────────────────────────────────────────────────────
const MEMORY_API_KEY = process.env.MEMORY_API_KEY;
const MEMORY_WORKSPACE_ID = process.env.MEMORY_WORKSPACE_ID;
const MEMORY_ENDPOINT = process.env.MEMORY_ENDPOINT; // optional: override default NAMS endpoint
const DEMO_USER_ID   = process.env.DEMO_USER_ID || process.env.DEMO_AGENT_ID || 'vercel-neo4j-notebook-agent';

if (!MEMORY_API_KEY) {
  console.error('ERROR: MEMORY_API_KEY is not set. Get a free key at https://memory.neo4jlabs.com');
  process.exit(1);
}

// ── NAMS memory client ────────────────────────────────────────────────────────
// workspaceId belongs on the client — it is sent as the X-Workspace-Id header on
// every request. Passing it to createConversation() does nothing: that call only
// accepts { userId, metadata }. Leave MEMORY_WORKSPACE_ID unset for the default
// workspace attached to the API key.
const memoryClient = new MemoryClient({
  apiKey: MEMORY_API_KEY,
  ...(MEMORY_WORKSPACE_ID ? { workspaceId: MEMORY_WORKSPACE_ID } : {}),
  ...(MEMORY_ENDPOINT     ? { endpoint:    MEMORY_ENDPOINT }     : {}),
});

// Create a new conversation session for this run
const conv = await memoryClient.shortTerm.createConversation({ userId: DEMO_USER_ID });
const convId = conv.id;
console.log(`Memory session: ${convId} (workspace: ${MEMORY_WORKSPACE_ID || 'default'})`);

// ── MCP client (Neo4j knowledge graph tools) ──────────────────────────────────
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
console.log('');

// ── Agent setup ───────────────────────────────────────────────────────────────
const model = await getModel();

const SYSTEM_PROMPT = `You are a helpful graph analyst with access to a Neo4j companies \
knowledge graph. Use the available tools to answer questions accurately.`;

// ── BEFORE hook: build context from NAMS ─────────────────────────────────────
async function buildContext(userQuery) {
  const contextParts = [];

  // Short-term: reflections, observations, recent messages
  const ctx = await memoryClient.shortTerm.getContext(convId);
  if (ctx.reflections?.length) {
    contextParts.push('Key insights:\n' + ctx.reflections.map(r => `- ${r.content}`).join('\n'));
  }
  if (ctx.recentMessages?.length) {
    contextParts.push('Recent messages:\n' + ctx.recentMessages.map(m => `${m.role.toUpperCase()}: ${m.content}`).join('\n'));
  }

  // Long-term: search entities relevant to this query
  const entities = await memoryClient.longTerm.searchEntities(userQuery, { limit: 5 });
  if (entities.length) {
    contextParts.push('Related knowledge from memory:\n' + entities.map(e => `- ${e.name}${e.description ? ': ' + e.description : ''}`).join('\n'));
    console.log(` ↳ Injecting ${entities.length} entity/entities from long-term memory.`);
  }

  if (!contextParts.length) return SYSTEM_PROMPT;

  console.log(` ↳ Injecting context: ${ctx.recentMessages?.length || 0} messages, ${entities.length} entities.`);
  return `${SYSTEM_PROMPT}\n\n--- MEMORY CONTEXT ---\n${contextParts.join('\n\n')}\n----------------------`;
}

// ── AFTER hook: save interaction to NAMS ──────────────────────────────────────
async function saveInteraction(userQuery, agentResponse) {
  await memoryClient.shortTerm.addMessage(convId, 'user', userQuery);
  await memoryClient.shortTerm.addMessage(convId, 'assistant', agentResponse);

  // Save as a long-term entity so it persists across sessions
  const title = `Research: ${userQuery.slice(0, 60)}${userQuery.length > 60 ? '…' : ''}`;
  await memoryClient.longTerm.addEntity(title, 'concept', { description: agentResponse.slice(0, 500) });
  console.log(' [Memory] Interaction saved to NAMS ✓');
}

// ── Run agent with memory hooks ───────────────────────────────────────────────
async function runWithMemory(query) {
  console.log(`\n[USER]: ${query}`);

  const systemWithContext = await buildContext(query);

  const { text } = await generateText({
    model,
    system:   systemWithContext,
    prompt:   query,
    tools:    mcp.tools,
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

// Turn 2: follow-up — NAMS context from Turn 1 is injected automatically
await runWithMemory(
  "Based on our conversation, what subsidiaries of the company we discussed appear in the database?"
);

await mcp.close();
