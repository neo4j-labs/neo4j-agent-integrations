import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  isStepCount,
  type ModelMessage,
  type UIMessage,
  type ToolSet,
} from 'ai';
import {
  createNams,
  createNamsProvider,
  enforceQueryMemory,
  findExistingConversation,
  makeClient,
} from '@neo4j-labs/nams-ai-provider';
import { HOOKS_SYSTEM_PROMPT, NO_MEMORY_SYSTEM_PROMPT, SYSTEM_PROMPT, TRANSPARENT_SYSTEM_PROMPT, buildDbToolsPrompt } from '@/lib/constants';
import { getNeo4jMcpTools, getNamsMcpConfig, isMcpConfigured, explainMcpError, guardTools } from '@/lib/neo4j-mcp';
import { CHAT_MODES, memoryMode, namsConfig, rawMode } from '@/lib/mode';

const MAX_STEPS = 10;
const MODEL_ID = process.env.OPENAI_MODEL || 'gpt-5.6-luna';
const TRANSCRIPT_LIMIT = 40;

// Optional: turn each saved memory into graph entities (tools mode only, one extra model call).
const EXTRACTION_MODEL_ID = process.env.NAMS_EXTRACTION_MODEL?.trim();
const extractionModel = EXTRACTION_MODEL_ID ? openai(EXTRACTION_MODEL_ID) : undefined;

function trim(text: string, max = 80): string {
  const s = text.replace(/\s+/g, ' ').trim();
  return s.length > max ? s.slice(0, max) + '…' : s;
}

function serialize(value: unknown, max = 2000): string | undefined {
  if (value === undefined) return undefined;
  const text = typeof value === 'string' ? value : JSON.stringify(value);
  if (text === undefined) return undefined;
  return text.length <= max ? text : `${text.slice(0, max)}… (truncated)`;
}

// Off mode only: the earlier turns of this chat, as the browser holds them.
function transcriptMessages(transcript: unknown): ModelMessage[] {
  if (!Array.isArray(transcript)) return [];
  return transcript
    .filter((m): m is { role: 'user' | 'assistant'; content: string } =>
      (m?.role === 'user' || m?.role === 'assistant') && typeof m?.content === 'string' && m.content.trim() !== '')
    .slice(-TRANSCRIPT_LIMIT)
    .map(m => ({ role: m.role, content: m.content }));
}

// On a re-run NAMS already holds the question and the answer being replaced, so drop both.
function withoutRerunTurn(history: ModelMessage[], userText: string): ModelMessage[] {
  const i = history.findLastIndex(m => m.role === 'user');
  const last = history[i]?.content;
  return typeof last === 'string' && last.trim() === userText.trim() ? history.slice(0, i) : history;
}

const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export async function POST(req: Request) {
  const reqStart = Date.now();

  // The browser sends only its newest message. Earlier turns come from NAMS.
  let body: {
    message?: UIMessage;
    trigger?: 'submit-message' | 'regenerate-message';
    sessionId?: string;
    userId?: string;
    conversationId?: string;
    transcript?: unknown;
  };
  try {
    body = await req.json();
  } catch {
    return json({ error: 'Invalid JSON in request body' }, 400);
  }

  const sessionId = body.sessionId?.trim() || 'default-session';
  const userId = body.userId?.trim() || sessionId;
  const conversationId = body.conversationId?.trim() || undefined;

  const userText = body.message?.role === 'user'
    ? body.message.parts
      .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
      .map(p => p.text)
      .join('')
    : '';
  if (!userText.trim()) return json({ error: 'The request has no user message.' }, 400);

  const mode = memoryMode();
  if (!mode) {
    return json({ error: `Unknown NAMS_MODE "${rawMode()}". Use ${CHAT_MODES.join(', ')}.` }, 503);
  }
  const memoryOn = mode !== 'off';
  const nams = namsConfig();
  if (memoryOn && !nams.apiKey) return json({ error: 'NAMS_API_KEY is not set. Check your .env.local file.' }, 503);

  const mcpEnabled = isMcpConfigured();
  const useExtraction = mode === 'tools' && Boolean(extractionModel);

  console.log(`\n${'═'.repeat(60)}`);
  console.log(
    `[chat] POST /api/chat  mode=${mode}  mcp=${mcpEnabled}  ` +
    `extraction=${useExtraction ? EXTRACTION_MODEL_ID : 'off'}`,
  );
  console.log(`[chat]   userId=${userId}  conv=${conversationId ?? 'auto'}  query="${trim(userText)}"`);

  const scope = { userId, conversationId };
  // Only tools mode uses the extraction model. The other modes would log a warning.
  const memoryConfig = useExtraction ? { ...nams, extractionModel } : nams;

  const resolvedModel = mode === 'provider'
    ? createNamsProvider({ ...memoryConfig, baseProvider: openai, scope }).languageModel(MODEL_ID)
    : mode === 'middleware'
      ? createNams(memoryConfig).wrap(openai(MODEL_ID), scope)
      : openai(MODEL_ID);

  // Memory modes read earlier turns through the hooks session. Start now, it overlaps the MCP connect.
  const session = memoryOn ? createNams(nams).hooks(scope) : undefined;
  const historyPromise: Promise<ModelMessage[]> = session ? session.loadSession() : Promise.resolve([]);

  // Every mode except tools connects MCP on its own.
  const mcpResult = mode !== 'tools' && mcpEnabled
    ? await getNeo4jMcpTools().catch(async (err) => {
      console.warn('[chat] Neo4j MCP connection failed:', await explainMcpError(err));
      return null;
    })
    : null;

  // Tools mode: memory tools and MCP tools come back together.
  const namsResult = mode === 'tools'
    ? await createNams(memoryConfig)
      .toolsWithMcp(scope, getNamsMcpConfig())
      .catch(async (err) => {
        console.warn('[chat] MCP unavailable, falling back to NAMS tools only:', await explainMcpError(err));
        return createNams(memoryConfig).toolsWithMcp(scope);
      })
    : null;

  // Close the MCP connections once, whether the turn finished or failed.
  let closed = false;
  const closeConnections = async () => {
    if (closed) return;
    closed = true;
    if (namsResult) await namsResult.close().catch((err) => console.warn('[chat] failed to close NAMS MCP:', err));
    if (mcpResult) await mcpResult.close().catch((err) => console.warn('[chat] failed to close Neo4j MCP:', err));
  };

  const rawTools = (namsResult?.tools ?? mcpResult?.tools) as ToolSet | undefined;
  const tools = rawTools ? guardTools(rawTools) : undefined;

  // Use the tools that actually connected, not the env vars.
  const dbToolNames = Object.keys(tools ?? {}).filter(
    name => name !== 'query_memory' && name !== 'store_memory',
  );
  const hasDbTools = dbToolNames.length > 0;
  // Only tools mode has memory tools, so only its prompts mention them.
  const basePrompt = !memoryOn ? NO_MEMORY_SYSTEM_PROMPT
    : mode === 'tools' ? SYSTEM_PROMPT
      : mode === 'hooks' ? HOOKS_SYSTEM_PROMPT
        : TRANSPARENT_SYSTEM_PROMPT;
  const systemPrompt = hasDbTools
    ? `${basePrompt}\n\n${buildDbToolsPrompt(dbToolNames, { memoryTools: mode === 'tools' })}`
    : basePrompt;

  if (mcpEnabled && !hasDbTools) {
    console.warn('[chat]   Neo4j MCP is configured but NOT connected — database questions cannot be answered.');
  }

  console.log(
    `[chat]   model=${MODEL_ID}  maxSteps=${MAX_STEPS}  tools=${Object.keys(tools ?? {}).length}` +
    (hasDbTools ? `  db=[${dbToolNames.join(', ')}]` : ''),
  );

  // Memory modes restore earlier turns from NAMS; off mode only has this chat's transcript.
  const history = memoryOn ? await historyPromise : transcriptMessages(body.transcript);
  console.log(memoryOn
    ? `[chat]   restored ${history.length} earlier turns from NAMS`
    : `[chat]   ${history.length} earlier turns from this chat (memory off)`);
  const earlierTurns = memoryOn && body.trigger === 'regenerate-message' ? withoutRerunTurn(history, userText) : history;
  const messages: ModelMessage[] = [...earlierTurns, { role: 'user', content: userText }];

  // Hooks mode: the app writes the why-trail, one NAMS reasoning step per agent step with its tool calls.
  async function saveReasoning(steps: any[]): Promise<void> {
    if (steps.length === 0) return;
    const client = makeClient(nams);
    const convId = await findExistingConversation(client, nams, scope).catch(() => null);
    if (!convId) return;

    for (const step of steps) {
      const calls: any[] = step.toolCalls ?? [];
      const results: any[] = step.toolResults ?? [];
      const errors: any[] = (step.content ?? []).filter((p: any) => p?.type === 'tool-error');
      const recorded = await client.reasoning.recordStep({
        conversationId: convId,
        reasoning: (step.reasoningText || step.text || '(the model emitted no reasoning for this step)').slice(0, 2000),
        actionTaken: calls.length ? calls.map(c => c.toolName).join(', ') : 'respond',
        result: calls.length ? `${calls.length} tool call(s)` : undefined,
      });
      for (const call of calls) {
        const error = errors.find(e => e.toolCallId === call.toolCallId);
        const output = results.find(r => r.toolCallId === call.toolCallId)?.output;
        // Hosted NAMS stores a non-string result as "", so always send a string.
        await client.reasoning.recordToolCall(recorded.id, call.toolName, call.input ?? {}, {
          result: serialize(error ? error.error : output),
          status: error ? 'failure' : 'success',
        });
      }
    }
  }

  try {
    const agent = new ToolLoopAgent({
      model: resolvedModel,
      instructions: systemPrompt,
      tools,
      // Ask OpenAI for reasoning summaries so the Reasoning Trace panel can show them.
      providerOptions: { openai: { reasoningSummary: 'auto' } },
      ...(namsResult ? { prepareStep: enforceQueryMemory({ graceSteps: 2 }) } : {}),
      stopWhen: (namsResult || mcpResult) ? isStepCount(MAX_STEPS) : isStepCount(1),
      onEnd: async ({ text, steps, usage, responseMessages }) => {
        try {
          const calls = steps.flatMap((s: any) => s.toolCalls ?? []).filter(Boolean);
          const queries = calls.filter((c: any) => c?.toolName === 'query_memory').length;
          const stores = calls.filter((c: any) => c?.toolName === 'store_memory').length;
          console.log(
            `[chat] Done | steps=${steps.length} queries=${queries} stores=${stores} ` +
            `elapsed=${Date.now() - reqStart}ms`,
          );
          if (usage) console.log(`[chat]   tokens in=${usage.inputTokens} out=${usage.outputTokens}`);
          if (text) console.log(`[chat]   response="${trim(text)}"`);

          // Hooks and tools modes save the turn here (before the trace, so a new user gets one conversation).
          if (session && mode === 'hooks') await session.onFinish({ prompt: userText })({ text, responseMessages });
          // Text only: tools-mode tool results are memory hits, and saving those again degrades recall.
          if (session && mode === 'tools') await session.onFinish({ prompt: userText })({ text });

          if (mode === 'hooks') {
            await saveReasoning(steps).catch(err => console.warn('[chat] failed to save the reasoning trail:', err));
          }
        } finally {
          await closeConnections();
        }
      },
    });

    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        try {
          const result = await agent.stream({ messages });
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
        } catch (err) {
          await closeConnections();
          throw err;
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
    await closeConnections();
    return json({ error: 'Failed to generate a response. Please try again.' }, 500);
  }
}
