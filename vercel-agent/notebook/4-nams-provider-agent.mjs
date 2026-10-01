/**
 * 4-nams-provider-agent.mjs — memory through @neo4j-labs/nams-ai-provider.
 *
 * NAMS_MODE picks how memory is added:
 *   provider   (default) memory is added around every model call
 *   middleware same, on a model you already have
 *   tools      the model calls query_memory / store_memory itself
 *   hooks      this script loads the conversation and saves each turn
 *
 * In every mode the earlier turns are loaded from NAMS, as in ../vercel_Nams_demo.
 *
 * Run:  NAMS_MODE=hooks node 4-nams-provider-agent.mjs
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
import { getMcpTools, getNamsMcpConfig, guardTools, isMcpConfigured, explainMcpError } from './mcp.mjs';
import {
  HOOKS_SYSTEM_PROMPT,
  MEMORY_SYSTEM_PROMPT,
  TRANSPARENT_SYSTEM_PROMPT,
  buildDbToolsPrompt,
} from './prompts.mjs';

// ── Configuration
const MAX_STEPS = 10;
const MODE      = (process.env.NAMS_MODE || 'provider').trim();
const USER_ID   = process.env.DEMO_USER_ID || process.env.DEMO_AGENT_ID || 'vercel-neo4j-notebook-agent';

const apiKey = process.env.MEMORY_API_KEY;
if (!apiKey) {
  console.error('ERROR: MEMORY_API_KEY is not set. Get a free key at https://memory.neo4jlabs.com');
  process.exit(1);
}

if (!['provider', 'middleware', 'tools', 'hooks'].includes(MODE)) {
  console.error(`ERROR: unknown NAMS_MODE "${MODE}". Use provider, middleware, tools, or hooks.`);
  process.exit(1);
}

// workspaceId is optional — omit it to use the default workspace behind the API key.
const memoryConfig = {
  apiKey,
  ...(process.env.MEMORY_WORKSPACE_ID ? { workspaceId: process.env.MEMORY_WORKSPACE_ID } : {}),
  ...(process.env.MEMORY_ENDPOINT     ? { endpoint:    process.env.MEMORY_ENDPOINT }     : {}),
};

// No conversationId, so each run picks up the user's latest conversation.
const scope = { userId: USER_ID };

const { provider, modelName } = await getProvider();

// ── Model and tools for the selected mode
const model = MODE === 'provider'
  ? createNamsProvider({ ...memoryConfig, baseProvider: provider, scope }).languageModel(modelName)
  : MODE === 'middleware'
    ? createNams(memoryConfig).wrap(provider(modelName), scope)
    : provider(modelName);

// Loads earlier turns in every mode. Hooks and tools mode also save through it.
const session = createNams(memoryConfig).hooks(scope);

// Every mode except tools connects MCP on its own.
const mcpResult = MODE !== 'tools' && isMcpConfigured()
  ? await getMcpTools().catch(async (err) => {
    console.warn('[nams] Neo4j MCP connection failed:', await explainMcpError(err));
    return null;
  })
  : null;

// Tools mode: memory tools and MCP tools come back together.
const namsResult = MODE === 'tools'
  ? await createNams(memoryConfig)
    .toolsWithMcp(scope, getNamsMcpConfig())
    .catch(async (err) => {
      console.warn('[nams] MCP unavailable, falling back to NAMS tools only:', await explainMcpError(err));
      return createNams(memoryConfig).toolsWithMcp(scope);
    })
  : null;

const tools = namsResult ? guardTools(namsResult.tools) : mcpResult?.tools;

// Use the tools that actually connected, not the env vars.
const dbToolNames = Object.keys(tools ?? {}).filter(
  name => name !== 'query_memory' && name !== 'store_memory',
);
const basePrompt = MODE === 'tools'
  ? MEMORY_SYSTEM_PROMPT
  : MODE === 'hooks' ? HOOKS_SYSTEM_PROMPT : TRANSPARENT_SYSTEM_PROMPT;
const systemPrompt = dbToolNames.length
  ? `${basePrompt}\n\n${buildDbToolsPrompt(dbToolNames, { memoryTools: MODE === 'tools' })}`
  : basePrompt;

if (isMcpConfigured() && !dbToolNames.length) {
  console.warn('[nams] Neo4j MCP is configured but NOT connected — database questions cannot be answered.');
}

console.log(`Mode:   ${MODE}`);
console.log(`Model:  ${modelName}`);
console.log(`Tools:  ${Object.keys(tools ?? {}).join(', ') || '(none — transparent memory)'}\n`);

// ── Agent
const memoryClient = makeClient(memoryConfig);

const agent = new ToolLoopAgent({
  model,
  instructions: systemPrompt,
  tools,
  ...(namsResult ? { prepareStep: enforceQueryMemory({ graceSteps: 2 }) } : {}),
  // Send the saved history plus this turn, and hand the prompt on to onFinish.
  prepareCall: async ({ options, prompt: _prompt, messages: _messages, ...settings }) => {
    const history = await session.loadSession();
    console.log(`  [nams] restored ${history.length} earlier turns`);
    return {
      ...settings,
      messages: [...history, { role: 'user', content: options.prompt }],
      runtimeContext: options,
    };
  },
  stopWhen: tools ? stepCountIs(MAX_STEPS) : stepCountIs(1),
  onFinish: async (event) => {
    const { steps, usage } = event;

    // Provider and middleware save the turn inside the model wrapper; the other two save it here.
    if (MODE === 'hooks') await session.onFinish()(event);
    // Text only: tools-mode tool results are memory hits, and saving those again degrades recall.
    if (MODE === 'tools') await session.onFinish()({ ...event, responseMessages: undefined });

    const calls   = steps.flatMap(s => s.toolCalls ?? []).filter(Boolean);
    const queries = calls.filter(c => c?.toolName === 'query_memory').length;
    const stores  = calls.filter(c => c?.toolName === 'store_memory').length;
    console.log(`  [nams] steps=${steps.length} queries=${queries} stores=${stores}` +
      (usage ? ` tokens in=${usage.inputTokens} out=${usage.outputTokens}` : ''));

    // One reasoning step per agent step, written in order.
    const convId = steps.length
      ? await resolveConversation(memoryClient, memoryConfig, scope).catch(() => '')
      : '';
    if (!convId) return;
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
      }).catch(err => console.warn('  [nams] failed to save a reasoning step:', err.message));
    }
  },
});

async function ask(query) {
  console.log(`\n[USER]:  ${query}`);
  const { text } = await agent.generate({ prompt: query, options: { prompt: query } });
  console.log(`[AGENT]: ${text}`);
  return text;
}

// ── Two-turn demo
try {
  await ask("I am conducting a competitive analysis of 'Google'. Tell me about their presence in the knowledge graph.");
  await ask('Based on our earlier conversation, which company was I researching, and what did you find?');
} finally {
  if (namsResult) await namsResult.close().catch(() => {});
  if (mcpResult)  await mcpResult.close().catch(() => {});
}
