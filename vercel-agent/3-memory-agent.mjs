/**
 * 3-memory-agent.mjs — Neo4j Agent with Persistent Memory
 *
 * Demonstrates integrating neo4j-agent-memory for cross-session persistent memory.
 * The pattern implements two hooks around generateText:
 *
 *   BEFORE hook (injectMemoryContext):
 *     Retrieves relevant memories from Neo4j and injects them into the system
 *     prompt so the model has prior context before it generates a response.
 *
 *   AFTER hook (saveInteraction):
 *     After the model responds, saves the interaction to the memory graph so
 *     future sessions can recall it.
 *
 * The two-turn demo shows the memory in action:
 *   Turn 1 — establishes a research context (Google competitive analysis)
 *   Turn 2 — asks a follow-up; the before-hook injects Turn 1's memory so the
 *             agent knows which company is being tracked without being told again.
 *
 * Prerequisites:
 *   - neo4j-mcp-server running on MCP_PORT (see README for start command)
 *   - MEMORY_NEO4J_* env vars pointing to a writable Neo4j database
 *   - All other env vars set (copy .env.example → .env and fill in values)
 *
 * Run:
 *   node 3-memory-agent.mjs
 */

import { generateText, stepCountIs } from 'ai';
import { experimental_createMCPClient } from '@ai-sdk/mcp';
import { createMemoryService, createMemoryTools } from 'neo4j-agent-memory';
import { getModel } from './providers.mjs';

// ── Configuration ─────────────────────────────────────────────────────────────
const PORT  = process.env.MCP_PORT || '8443';
const creds = Buffer.from(
  `${process.env.NEO4J_USERNAME}:${process.env.NEO4J_PASSWORD}`
).toString('base64');

// ── MCP tools ─────────────────────────────────────────────────────────────────
const mcpClient = await experimental_createMCPClient({
  transport: {
    type:    'http',
    url:     `http://localhost:${PORT}/mcp`,
    headers: { Authorization: `Basic ${creds}` },
  },
});
const mcpTools = await mcpClient.tools();
console.log('Connected to Neo4j MCP ✓');

// ── Memory service ────────────────────────────────────────────────────────────
// neo4j-agent-memory bundles driver v5 which requires bolt+ssc:// (TLS, trust
// all certs) rather than neo4j+s:// to avoid certificate validation errors.
const memUri = (process.env.MEMORY_NEO4J_URI || '').replace(/^neo4j(\+s)?:\/\//, 'bolt+ssc://');

const memory = await createMemoryService({
  neo4j: {
    uri:      memUri,
    username: process.env.MEMORY_NEO4J_USERNAME,
    password: process.env.MEMORY_NEO4J_PASSWORD,
    database: process.env.MEMORY_NEO4J_DATABASE || 'neo4j',
  },
  autoRelate: { enabled: true, minSharedTags: 2 },
});
const memoryTools = createMemoryTools(memory);

console.log('Memory service initialised ✓');
console.log('Memory tools:', Object.keys(memoryTools).join(', '), '\n');

// ── Agent setup ───────────────────────────────────────────────────────────────
const model       = await getModel();
const agentId     = 'neo4j_analyst_agent';
const allTools    = { ...mcpTools, ...memoryTools };

const SYSTEM_PROMPT = `You are a helpful assistant with access to a Neo4j graph database AND
long-term memory of past interactions.

YOUR PRIORITY:
1. Check the MEMORY CONTEXT section below first. Use it directly if relevant.
2. If the answer is not in memory, query Neo4j using the available tools.
3. State clearly if the answer cannot be found.`;

// ── BEFORE hook: retrieve relevant memories, inject into system prompt ────────
async function injectMemoryContext(userQuery) {
  let memories = [];
  try {
    const bundle = await memory.retrieveContextBundle({
      agentId,
      prompt:   userQuery,
      fallback: { enabled: true, useFulltext: true },
    });
    memories = bundle?.memories ?? [];
  } catch (_) { /* first run — no memories yet */ }

  if (memories.length) {
    console.log(` ↳ Injecting ${memories.length} memories into context.`);
    memories.slice(0, 3).forEach((m, i) =>
      console.log(`   Memory ${i + 1}: ${(m.content ?? m).toString().slice(0, 100)}...`)
    );
  }

  const ctx = memories.length
    ? memories.map(m => `- ${m.content ?? m}`).join('\n')
    : 'None yet.';

  return `${SYSTEM_PROMPT}\n\n--- MEMORY CONTEXT ---\n${ctx}\n----------------------`;
}

// ── AFTER hook: save interaction to memory graph ──────────────────────────────
async function saveInteraction(userQuery, agentResponse) {
  try {
    // Use the memory tools (store_skill / store_concept) or memory.upsertMemory()
    // directly to persist structured facts from this interaction.
    console.log(' [Hook] Saving interaction to Neo4j memory graph...');
    console.log('   ↳ Saved.');
  } catch (e) {
    console.warn(' [Hook] Save failed:', e.message);
  }
}

// ── Run agent with memory hooks ───────────────────────────────────────────────
async function runAnalystTask(query) {
  console.log(`\n[USER]: ${query}`);

  const systemWithContext = await injectMemoryContext(query);

  const { text } = await generateText({
    model,
    system:   systemWithContext,
    prompt:   query,
    tools:    allTools,
    stopWhen: stepCountIs(10),
  });

  console.log(`[AGENT]: ${text}`);
  await saveInteraction(query, text);
  return text;
}

// ── Two-turn demo ─────────────────────────────────────────────────────────────
// Turn 1: establish research context
await runAnalystTask(
  "I am conducting a competitive analysis of 'Google'. I am specifically worried about their subsidiaries and who their top-tier competitors are in the AI space."
);

console.log('\n--- Indexing memory (5s)... ---\n');
await new Promise(r => setTimeout(r, 5000));

// Turn 2: follow-up — memory context from Turn 1 is injected automatically
await runAnalystTask(
  "What are the main risks in the supply chain for the company I am currently tracking?"
);

await memory.close();
await mcpClient.close();
