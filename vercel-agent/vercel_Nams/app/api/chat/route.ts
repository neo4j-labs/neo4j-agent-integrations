import { openai }   from '@ai-sdk/openai';
import {
  streamText,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
  type UIMessage,
} from 'ai';
import { createNams, type NamsMode } from '@/lib/nams';
import { SYSTEM_PROMPT }             from '@/lib/constants';

// ─── Integration mode
//
//   NAMS_MODE=provider  (default)
//     createNams().wrap(model, scope) — transparent LanguageModelV3Middleware.
//     Memory is retrieved and injected into the prompt before each call, and the
//     turn is persisted after. The model never sees tool definitions; no `tools:`
//     field is needed. Closest to the Mem0 / Letta pattern.
//
//   NAMS_MODE=tools
//     createNams().tools(scope) — query_memory + store_memory as AI SDK tool()s.
//     The model decides when to call them. Pair with SYSTEM_PROMPT that instructs
//     query → answer → store. Closest to the Supermemory pattern.
//
// ─────────────────────────────────────────────────────────────────────────────

export const runtime = 'nodejs';

const MAX_STEPS = 10;
const MODEL_ID  = process.env.OPENAI_MODEL || 'gpt-4o-mini';

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
    messages:        UIMessage[];
    sessionId?:      string;
    userId?:         string;
    conversationId?: string;
  };
  try {
    body = await req.json();
  } catch {
    return json({ error: 'Invalid JSON in request body' }, 400);
  }

  const uiMessages:  UIMessage[] = body.messages ?? [];
  const sessionId    = body.sessionId?.trim()      || 'default-session';
  const userId       = body.userId?.trim()          || sessionId;
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
      role:    m.role as 'user' | 'assistant',
      content: m.parts
        .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
        .map(p => p.text)
        .join(''),
    }))
    .filter(m => m.content);

  const apiKey = process.env.MEMORY_API_KEY ?? '';
  if (!apiKey) return json({ error: 'MEMORY_API_KEY is not set. Check your .env.local file.' }, 503);

  const mode = ((process.env.NAMS_MODE ?? 'provider').trim()) as NamsMode;

  console.log(`\n${'═'.repeat(60)}`);
  console.log(`[chat] POST /api/chat  mode=${mode}`);
  console.log(`[chat]   userId=${userId}  conv=${conversationId ?? 'auto'}  query="${trim(userText)}"`);

  const nams = createNams({
    apiKey,
    workspaceId: process.env.MEMORY_WORKSPACE_ID,
  });

  const scope = { userId, conversationId };

  //
  // MODE 1 — Provider: wrap the model; no tools: needed.
  // MODE 2 — Tools: pass tool objects; model drives memory.
  //
  const resolvedModel = mode === 'provider'
    ? nams.wrap(openai(MODEL_ID), scope)
    : openai(MODEL_ID);

  const tools = mode === 'tools'
    ? nams.tools(scope)
    : undefined;

  console.log(`[chat]   model=${MODEL_ID}  maxSteps=${MAX_STEPS}`);

  try {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        const result = streamText({
          model:    resolvedModel,
          system:   SYSTEM_PROMPT,
          messages: coreMessages,
          tools,
          stopWhen: mode === 'tools' ? stepCountIs(MAX_STEPS) : undefined,
          onFinish: async ({ text, steps, usage }) => {
            const calls   = steps.flatMap(s => s.toolCalls ?? []);
            const queries = calls.filter(c => c.toolName === 'query_memory').length;
            const stores  = calls.filter(c => c.toolName === 'store_memory').length;
            console.log(
              `[chat] Done | steps=${steps.length} queries=${queries} stores=${stores} ` +
              `elapsed=${Date.now() - reqStart}ms`,
            );
            if (usage) console.log(`[chat]   tokens in=${usage.inputTokens} out=${usage.outputTokens}`);
            if (text)  console.log(`[chat]   response="${trim(text)}"`);

            if (steps.length > 0 && mode === 'tools') {
              const { makeClient: mk, resolveConversation: rc } = await import('@/lib/nams');
              const client = mk({ apiKey, workspaceId: process.env.MEMORY_WORKSPACE_ID });
              const convId = await rc(client, { apiKey, workspaceId: process.env.MEMORY_WORKSPACE_ID }, scope)
                .catch(() => '');
              if (convId) {
                steps.forEach((step, i) => {
                  const toolNames = (step.toolCalls ?? []).map((c: any) => c.toolName).join(', ');
                  const reasoning = (step.text || `Step ${i + 1}${toolNames ? ` — ${toolNames}` : ''}`).slice(0, 500);
                  const actionTaken = toolNames || 'direct response';
                  const result = (step.toolResults ?? [])
                    .map((r: any) => JSON.stringify(r?.output ?? r).slice(0, 150))
                    .join('; ')
                    .slice(0, 500);
                  client.reasoning
                    .recordStep({ conversationId: convId, reasoning, actionTaken, result })
                    .catch(() => {});
                });
              }
            }
          },
        });

        writer.merge(result.toUIMessageStream());
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
