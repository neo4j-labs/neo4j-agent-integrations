import { openai } from '@ai-sdk/openai';
import {
  streamText,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
  type UIMessage,
} from 'ai';
import {
  NamsMemoryProvider,
  getOrCreateConversation,
  type NamsMemoryOptions,
} from '@/lib/nams-memory-provider';
import { SYSTEM_PROMPT } from '@/lib/constants';

export const runtime = 'nodejs';

const MAX_STEPS = 10;

function trim(text: string, maxLen = 80): string {
  const s = text.replace(/\s+/g, ' ').trim();
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
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
  const sessionId    = body.sessionId?.trim()     || 'default-session';
  // userId is the stable browser identity from the sessions cookie.
  // Fall back to sessionId for backward compatibility.
  const userId       = body.userId?.trim()        || sessionId;
  const existingConv = body.conversationId?.trim() || undefined;

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

  console.log(`\n${'═'.repeat(60)}`);
  console.log(`[chat] ① POST /api/chat`);
  console.log(`[chat]   session: ${sessionId} | userId: ${userId} | existingConv: ${existingConv ?? 'none'}`);
  console.log(`[chat]   query: "${trim(userText)}"`);

  const memoryOptions: NamsMemoryOptions = {
    apiKey:         process.env.MEMORY_API_KEY ?? '',
    userId,
    conversationId: existingConv,
    workspaceId:    process.env.MEMORY_WORKSPACE_ID,
  };

  if (!memoryOptions.apiKey) {
    return json({ error: 'MEMORY_API_KEY is not set. Check your .env.local file.' }, 503);
  }

  let namsClient: Awaited<ReturnType<typeof getOrCreateConversation>>['client'];
  let convId: string;
  try {
    ({ client: namsClient, convId } = await getOrCreateConversation(memoryOptions));
    console.log(`[chat] ② Conversation resolved: ${convId}`);
  } catch (e) {
    console.error('[chat] Failed to resolve NAMS conversation:', e);
    return json({ error: 'Memory service unavailable. Please try again.' }, 503);
  }

  const memory = new NamsMemoryProvider(memoryOptions);
  const tools = memory.tools();

  if (userText) {
    namsClient.shortTerm.addMessage(convId, 'user', userText)
      .then(() => console.log(`[chat]   ✓ User message stored to short-term`))
      .catch((e: unknown) => console.warn('[chat]   User message ingest failed:', e));
  }

  const model = process.env.OPENAI_MODEL || 'gpt-4o-mini';
  console.log(`[chat] ③ Agent | model: ${model} | maxSteps: ${MAX_STEPS}`);

  try {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        // Send the NAMS conversation ID so the client can reuse it on the next request
        writer.write({ type: 'data-conversation-id', data: convId } as any);

        const result = streamText({
          model:    openai(model),
          system:   SYSTEM_PROMPT,
          messages: coreMessages,
          tools,
          stopWhen: stepCountIs(MAX_STEPS),
          onFinish: async ({ text, steps, usage }) => {
            const calls   = steps.flatMap(s => s.toolCalls ?? []);
            const queries = calls.filter(c => c.toolName === 'query_memory').length;
            const stores  = calls.filter(c => c.toolName === 'store_memory').length;
            const elapsed = Date.now() - reqStart;
            console.log(`[chat] ④ Done | steps: ${steps.length} | 🔍 ×${queries} | 💾 ×${stores} | ${elapsed}ms`);
            if (usage) console.log(`[chat]   tokens: input=${usage.inputTokens} output=${usage.outputTokens}`);
            if (text)  console.log(`[chat]   response: "${trim(text)}"`);

            if (text) {
              namsClient.shortTerm.addMessage(convId, 'assistant', text)
                .then(() => console.log(`[chat]   ✓ Assistant response stored to short-term`))
                .catch((e: unknown) => console.error('[chat]   Failed to persist assistant message:', e));
            }

            if (steps.length > 0) {
              console.log(`[chat]   Recording ${steps.length} reasoning step(s) to NAMS…`);
              steps.forEach((step, i) => {
                const toolNames    = (step.toolCalls ?? []).map((c: { toolName: string }) => c.toolName).join(', ');
                const resultSummary = (step.toolResults ?? [])
                  .map((r: unknown) => JSON.stringify((r as { output?: unknown }).output ?? r).slice(0, 150))
                  .join('; ');
                const reasoning   = (step.text || `Step ${i + 1}${toolNames ? ` — ${toolNames}` : ''}`).slice(0, 500);
                const actionTaken = toolNames || 'direct response';
                const result      = (resultSummary || step.text || '').slice(0, 500);
                console.log(`[chat]   step ${i + 1}: action="${actionTaken}" | reasoning="${trim(reasoning)}"`);
                namsClient.reasoning.recordStep({ conversationId: convId, reasoning, actionTaken, result })
                  .then(() => console.log(`[chat]   ✓ Step ${i + 1} recorded to reasoning trace`))
                  .catch((e: unknown) => console.error(`[chat]   Failed to record reasoning step ${i + 1}:`, e));
              });
            }
          },
        });

        writer.merge(result.toUIMessageStream());
      },
      onError: (err) => {
        console.error('[chat] Stream error:', err);
        return 'Something went wrong. Please try again.';
      },
    });

    return createUIMessageStreamResponse({ stream });
  } catch (err) {
    console.error('[chat] Failed to start stream:', err);
    return json({ error: 'Failed to generate a response. Please try again.' }, 500);
  }
}
