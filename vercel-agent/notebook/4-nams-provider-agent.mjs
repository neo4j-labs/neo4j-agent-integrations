/**
 * 4-nams-provider-agent.mjs — NAMS via @neo4j-labs/nams-ai-provider
 *
 * The packaged counterpart to 3-memory-agent.mjs: instead of hand-writing the
 * before/after memory hooks, the package wires NAMS into the AI SDK for you.
 * This is the exact integration the Next.js demo in ../vercel_Nams_demo runs —
 * see its app/api/chat/route.ts.
 *
 * ─── Integration modes (NAMS_MODE) ───────────────────────────────────────────
 *
 *   NAMS_MODE=provider  (default)
 *     createNamsProvider({ baseProvider, ... }).languageModel(id) — a registrable
 *     ProviderV3. Memory is retrieved and injected into the prompt before each
 *     call and the turn is persisted after. The model never sees memory tools.
 *
 *   NAMS_MODE=middleware
 *     createNams().wrap(model, scope) — same transparent memory, but decorating
 *     an already-resolved model instance instead of a provider.
 *
 *   NAMS_MODE=tools
 *     createNams().toolsWithMcp(scope, mcpConfig) — query_memory + store_memory
 *     as AI SDK tool()s, merged with the Neo4j MCP tools. The model decides when
 *     to call them; enforceQueryMemory() guarantees query_memory runs before the
 *     final answer.
 *
 * Prerequisites:
 *   - MEMORY_API_KEY set (free key at memory.neo4jlabs.com)
 *   - MCP_URL / MCP_PORT + MCP auth vars for graph access (optional — without
 *     them the agent still runs, memory-only)
 *
 * Run:
 *   node 4-nams-provider-agent.mjs
 *   NAMS_MODE=tools node 4-nams-provider-agent.mjs
 */

import dotenv from 'dotenv';
dotenv.config();

import { ToolLoopAgent, stepCountIs } from 'ai';
import {
  createNams,
  createNamsProvider,
  enforceQueryMemory,
  makeClient,
  resolveConversation,
} from '@neo4j-labs/nams-ai-provider';
import { getProvider } from './providers.mjs';
import { getMcpTools, getNamsMcpConfig, isMcpConfigured, explainMcpError } from './mcp.mjs';
import { MEMORY_SYSTEM_PROMPT, TRANSPARENT_SYSTEM_PROMPT, buildDbToolsPrompt } from './prompts.mjs';

// ── Configuration ─────────────────────────────────────────────────────────────
const MAX_STEPS = 10;
const MODE      = (process.env.NAMS_MODE || 'provider').trim();
const USER_ID   = process.env.DEMO_USER_ID || process.env.DEMO_AGENT_ID || 'vercel-neo4j-notebook-agent';

const apiKey = process.env.MEMORY_API_KEY;
if (!apiKey) {
  console.error('ERROR: MEMORY_API_KEY is not set. Get a free key at https://memory.neo4jlabs.com');
  process.exit(1);
}

if (!['provider', 'middleware', 'tools'].includes(MODE)) {
  console.error(`ERROR: unknown NAMS_MODE "${MODE}". Use provider, middleware, or tools.`);
  process.exit(1);
}

// workspaceId is optional — omit it to use the default workspace behind the API key.
const memoryConfig = {
  apiKey,
  ...(process.env.MEMORY_WORKSPACE_ID ? { workspaceId: process.env.MEMORY_WORKSPACE_ID } : {}),
  ...(process.env.MEMORY_ENDPOINT     ? { endpoint:    process.env.MEMORY_ENDPOINT }     : {}),
};

// One scope per user session. Omitting conversationId lets NAMS resume the
// user's most recent conversation instead of starting a fresh one each run —
// which is what makes memory survive across `node 4-...` invocations.
const scope = { userId: USER_ID };

const { provider, modelName } = await getProvider();

// ── Resolve model + tools for the selected mode ───────────────────────────────
const model = MODE === 'provider'
  ? createNamsProvider({ ...memoryConfig, baseProvider: provider, scope }).languageModel(modelName)
  : MODE === 'middleware'
    ? createNams(memoryConfig).wrap(provider(modelName), scope)
    : provider(modelName);

// Provider / middleware modes: MCP is a separate connection — memory is transparent.
const mcpResult = MODE !== 'tools' && isMcpConfigured()
  ? await getMcpTools().catch(async (err) => {
    console.warn('[nams] Neo4j MCP connection failed:', await explainMcpError(err));
    return null;
  })
  : null;

// Tools mode: toolsWithMcp merges NAMS memory tools + MCP tools into one set.
const namsResult = MODE === 'tools'
  ? await createNams(memoryConfig)
    .toolsWithMcp(scope, getNamsMcpConfig())
    .catch(async (err) => {
      console.warn('[nams] MCP unavailable, falling back to NAMS tools only:', await explainMcpError(err));
      return createNams(memoryConfig).toolsWithMcp(scope);
    })
  : null;

const tools = namsResult?.tools ?? mcpResult?.tools;

// Derive the DB tool names from what actually came back, rather than inferring
// "connected" from the env vars — a 401 still leaves isMcpConfigured() true.
const dbToolNames = Object.keys(tools ?? {}).filter(
  name => name !== 'query_memory' && name !== 'store_memory',
);
const basePrompt = MODE === 'tools' ? MEMORY_SYSTEM_PROMPT : TRANSPARENT_SYSTEM_PROMPT;
const systemPrompt = dbToolNames.length
  ? `${basePrompt}\n\n${buildDbToolsPrompt(dbToolNames)}`
  : basePrompt;

if (isMcpConfigured() && !dbToolNames.length) {
  console.warn('[nams] Neo4j MCP is configured but NOT connected — database questions cannot be answered.');
}

console.log(`Mode:   ${MODE}`);
console.log(`Model:  ${modelName}`);
console.log(`Tools:  ${Object.keys(tools ?? {}).join(', ') || '(none — transparent memory)'}\n`);

// ── Agent ─────────────────────────────────────────────────────────────────────
const memoryClient = makeClient(memoryConfig);

const agent = new ToolLoopAgent({
  model,
  instructions: systemPrompt,
  tools,
  // enforceQueryMemory only applies in tools mode — it needs query_memory to exist.
  ...(namsResult ? { prepareStep: enforceQueryMemory({ graceSteps: 2 }) } : {}),
  stopWhen: tools ? stepCountIs(MAX_STEPS) : stepCountIs(1),
  onFinish: async ({ steps, usage }) => {
    const calls   = steps.flatMap(s => s.toolCalls ?? []).filter(Boolean);
    const queries = calls.filter(c => c?.toolName === 'query_memory').length;
    const stores  = calls.filter(c => c?.toolName === 'store_memory').length;
    console.log(`  [nams] steps=${steps.length} queries=${queries} stores=${stores}` +
      (usage ? ` tokens in=${usage.inputTokens} out=${usage.outputTokens}` : ''));

    // Persist the step trace so a later session can recall *how* an answer was reached.
    if (steps.length) {
      const convId = await resolveConversation(memoryClient, memoryConfig, scope).catch(() => '');
      if (convId) {
        for (const [i, step] of steps.entries()) {
          const toolNames = (step.toolCalls ?? []).map(c => c.toolName).join(', ');
          await memoryClient.reasoning.recordStep({
            conversationId: convId,
            reasoning:      (step.text || `Step ${i + 1}${toolNames ? ` — ${toolNames}` : ''}`).slice(0, 500),
            actionTaken:    toolNames || 'direct response',
            result:         (step.toolResults ?? [])
              .map(r => JSON.stringify(r?.output ?? r).slice(0, 150))
              .join('; ')
              .slice(0, 500),
          }).catch(() => {});
        }
      }
    }
  },
});

async function ask(query) {
  console.log(`\n[USER]:  ${query}`);
  const { text } = await agent.generate({ prompt: query });
  console.log(`[AGENT]: ${text}`);
  return text;
}

// ── Two-turn demo ─────────────────────────────────────────────────────────────
// Turn 1 establishes the research context; Turn 2 relies on NAMS to recall it.
// Re-run the script and Turn 2 still works — memory outlives the process.
await ask("I am conducting a competitive analysis of 'Google'. Tell me about their presence in the knowledge graph.");
await ask('Based on our earlier conversation, which company was I researching, and what did you find?');

if (namsResult) await namsResult.close().catch(() => {});
if (mcpResult)  await mcpResult.close().catch(() => {});
