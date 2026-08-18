import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  defaultSettingsMiddleware,
  stepCountIs,
  wrapLanguageModel,
  type UIMessage,
  type ToolSet,
  type PrepareStepFunction,
} from 'ai';
import { createNams, createNamsProvider, enforceQueryMemory, type NamsMode } from '@neo4j-labs/nams-ai-provider';
import { SYSTEM_PROMPT, TRANSPARENT_SYSTEM_PROMPT, buildDbToolsPrompt } from '@/lib/constants';
import { getNeo4jMcpTools, getNamsMcpConfig, isMcpConfigured, explainMcpError, capToolOutputs } from '@/lib/neo4j-mcp';
import { ensureStored } from '@/lib/nams-enrich';

const MAX_STEPS = 10;
const MODEL_ID = process.env.OPENAI_MODEL || 'gpt-5.4-mini';

// Optional entity extraction. When set, every stored memory is decomposed into
// graph entities and relationships — "Alex works at TechCorp" becomes
// (Alex:Person)-[:WORKS_AT]->(TechCorp:Organization) — at the cost of one extra
// model call per stored memory. Off by default, matching the package default.
const EXTRACTION_MODEL_ID = process.env.NAMS_EXTRACTION_MODEL?.trim();

const extractionModel = EXTRACTION_MODEL_ID
  ? wrapLanguageModel({
    model: openai(EXTRACTION_MODEL_ID),
    middleware: defaultSettingsMiddleware({
      settings: { providerOptions: { openai: { strictJsonSchema: false } } },
    }),
  })
  : undefined;

function trim(text: string, max = 80): string {
  const s = text.replace(/\s+/g, ' ').trim();
  return s.length > max ? s.slice(0, max) + '…' : s;
}

const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export async function POST(req: Request) {
  const reqStart = Date.now();

  let body: {
    messages: UIMessage[];
    sessionId?: string;
    userId?: string;
    conversationId?: string;
  };
  try {
    body = await req.json();
  } catch {
    return json({ error: 'Invalid JSON in request body' }, 400);
  }

  const uiMessages: UIMessage[] = body.messages ?? [];
  const sessionId = body.sessionId?.trim() || 'default-session';
  const userId = body.userId?.trim() || sessionId;
  const conversationId = body.conversationId?.trim() || undefined;

  const lastUser = [...uiMessages].reverse().find(m => m.role === 'user');
  const userText = lastUser
    ? lastUser.parts
      .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
      .map(p => p.text)
      .join('')
    : '';

  const coreMessages = uiMessages
    .filter(m => m.role === 'user' || m.role === 'assistant')
    .map(m => ({
      role: m.role as 'user' | 'assistant',
      content: m.parts
        .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
        .map(p => p.text)
        .join(''),
    }))
    .filter(m => m.content);

  const apiKey = process.env.MEMORY_API_KEY ?? '';
  if (!apiKey) return json({ error: 'MEMORY_API_KEY is not set. Check your .env.local file.' }, 503);

  const mode = ((process.env.NAMS_MODE ?? 'provider').trim()) as NamsMode;
  const mcpEnabled = isMcpConfigured();

  console.log(`\n${'═'.repeat(60)}`);
  console.log(
    `[chat] POST /api/chat  mode=${mode}  mcp=${mcpEnabled}  ` +
    `extraction=${EXTRACTION_MODEL_ID ?? 'off'}`,
  );
  console.log(`[chat]   userId=${userId}  conv=${conversationId ?? 'auto'}  query="${trim(userText)}"`);

  const scope = { userId, conversationId };
  const memoryConfig = {
    apiKey,
    workspaceId: process.env.MEMORY_WORKSPACE_ID,
    ...(extractionModel ? { extractionModel } : {}),
  };

  //
  const resolvedModel = mode === 'provider'
    ? createNamsProvider({ ...memoryConfig, baseProvider: openai, scope }).languageModel(MODEL_ID)
    : mode === 'middleware'
      ? createNams(memoryConfig).wrap(openai(MODEL_ID), scope)
      : openai(MODEL_ID);

  // Provider / middleware modes: MCP connection is separate (transparent memory handles itself)
  const mcpResult = (mode === 'provider' || mode === 'middleware') && mcpEnabled
    ? await getNeo4jMcpTools().catch(async (err) => {
      console.warn('[chat] Neo4j MCP connection failed:', await explainMcpError(err));
      return null;
    })
    : null;

  // Tools mode: toolsWithMcp merges NAMS memory tools + MCP into one call
  const namsResult = mode === 'tools'
    ? await createNams(memoryConfig)
      .toolsWithMcp(scope, getNamsMcpConfig())
      .catch(async (err) => {
        console.warn('[chat] MCP unavailable, falling back to NAMS tools only:', await explainMcpError(err));
        return createNams(memoryConfig).toolsWithMcp(scope);
      })
    : null;

  const rawTools = (namsResult?.tools ?? mcpResult?.tools) as ToolSet | undefined;
  const tools = rawTools ? capToolOutputs(rawTools) : undefined;

  // Derive the DB tool names from what actually came back, rather than inferring
  // "connected" from the env vars — a 401 still leaves mcpEnabled true.
  const dbToolNames = Object.keys(tools ?? {}).filter(
    name => name !== 'query_memory' && name !== 'store_memory',
  );
  const hasDbTools = dbToolNames.length > 0;
  // provider/middleware: memory tools don't exist, model must never be told to call them.
  // tools: query_memory/store_memory are real tools the model drives explicitly.
  const basePrompt = mode === 'tools' ? SYSTEM_PROMPT : TRANSPARENT_SYSTEM_PROMPT;
  const systemPrompt = hasDbTools
    ? `${basePrompt}\n\n${buildDbToolsPrompt(dbToolNames)}`
    : basePrompt;

  if (mcpEnabled && !hasDbTools) {
    console.warn('[chat]   Neo4j MCP is configured but NOT connected — database questions cannot be answered.');
  }

  console.log(
    `[chat]   model=${MODEL_ID}  maxSteps=${MAX_STEPS}  tools=${Object.keys(tools ?? {}).length}` +
    (hasDbTools ? `  db=[${dbToolNames.join(', ')}]` : ''),
  );

  try {
    const agent = new ToolLoopAgent({
      model: resolvedModel,
      instructions: systemPrompt,
      tools,
      ...(namsResult
        ? { prepareStep: enforceQueryMemory({ graceSteps: 2 }) as unknown as PrepareStepFunction<ToolSet> }
        : {}),
      stopWhen: (namsResult || mcpResult) ? stepCountIs(MAX_STEPS) : stepCountIs(1),
      onFinish: async ({ text, steps, usage }: { text: string; steps: any[]; usage: any }) => {
        const calls = steps.flatMap((s: any) => s.toolCalls ?? []).filter(Boolean);
        const queries = calls.filter((c: any) => c?.toolName === 'query_memory').length;
        const stores = calls.filter((c: any) => c?.toolName === 'store_memory').length;
        console.log(
          `[chat] Done | steps=${steps.length} queries=${queries} stores=${stores} ` +
          `elapsed=${Date.now() - reqStart}ms`,
        );
        if (usage) console.log(`[chat]   tokens in=${usage.inputTokens} out=${usage.outputTokens}`);
        if (text) console.log(`[chat]   response="${trim(text)}"`);
        if (namsResult && stores === 0) {
          const wrote = await ensureStored(tools, userText);
          if (wrote) console.log('[chat]   store_memory skipped by model — persisted turn in onFinish');
        }

        if (steps.length > 0) {
          const { makeClient: mk, resolveConversation: rc } = await import('@neo4j-labs/nams-ai-provider');
          const client = mk({ apiKey, workspaceId: process.env.MEMORY_WORKSPACE_ID });
          const convId = await rc(client, { apiKey, workspaceId: process.env.MEMORY_WORKSPACE_ID }, scope)
            .catch(() => '');
          if (convId) {
            steps.forEach((step: any, i: number) => {
              const toolNames = (step.toolCalls ?? []).map((c: any) => c.toolName).join(', ');
              const reasoning = (step.text || `Step ${i + 1}${toolNames ? ` — ${toolNames}` : ''}`).slice(0, 500);
              const actionTaken = toolNames || 'direct response';
              const result = (step.toolResults ?? [])
                .map((r: any) => JSON.stringify(r?.output ?? r).slice(0, 150))
                .join('; ')
                .slice(0, 500);
              client.reasoning
                .recordStep({ conversationId: convId, reasoning, actionTaken, result })
                .catch(() => { });
            });
          }
        }

        if (namsResult) await namsResult.close().catch(() => { });
        if (mcpResult) await mcpResult.close().catch(() => { });
      },
    });

    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        const result = await agent.stream({ messages: coreMessages });
        writer.merge(result.toUIMessageStream());
        const [text, finishReason] = await Promise.all([
          Promise.resolve(result.text).catch(() => ''),
          Promise.resolve(result.finishReason).catch(() => 'unknown' as const),
        ]);
        if (!(text ?? '').trim()) {
          console.warn(`[chat] Empty answer (finishReason=${finishReason}) — emitting fallback text`);
          const id = 'fallback-text';
          writer.write({ type: 'text-start', id });
          writer.write({
            type: 'text-delta',
            id,
            delta: finishReason === 'tool-calls'
              ? `I ran out of steps (max ${MAX_STEPS}) before I could answer. Please try rephrasing your question.`
              : 'I was not able to produce an answer for that. Please try again.',
          });
          writer.write({ type: 'text-end', id });
        }
      },
      onError: (err) => {
        console.error('[chat] stream error:', err);
        return 'Something went wrong. Please try again.';
      },
    });

    return createUIMessageStreamResponse({ stream });
  } catch (err) {
    console.error('[chat] Failed to start stream:', err);
    return json({ error: 'Failed to generate a response. Please try again.' }, 500);
  }
}
