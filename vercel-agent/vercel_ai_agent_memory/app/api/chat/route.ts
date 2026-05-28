
import { openai } from '@ai-sdk/openai';
import {
  streamText,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from 'ai';
import { getMemoryClient, ensureConversation, searchMemoryContext } from '@/Chat/chat';
import { BASE_SYSTEM_PROMPT } from '@/lib/constants';
import { generateTitle } from '@/lib/title';
import type { HistoryMsg } from '@/lib/types';

export const runtime = 'nodejs';

const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('sessionId');
  const existingConversationId = searchParams.get('conversationId') ?? undefined;
  if (!sessionId) return json({ error: 'Missing sessionId' }, 400);

  let conversationId: string;
  try {
    conversationId = await ensureConversation(sessionId, existingConversationId);
  } catch {
    return json({ messages: [], conversationId: null }, 200);
  }

  try {
    const ctx = await getMemoryClient().shortTerm.getContext(conversationId);
    const uiMessages: UIMessage[] = [...ctx.recentMessages]
      .reverse()
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m, i) => ({
        id: `history-${i}`,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        parts: [{ type: 'text' as const, text: m.content }],
      }));
    return json({ messages: uiMessages, conversationId }, 200);
  } catch {
    return json({ messages: [], conversationId }, 200);
  }
}

export async function DELETE(req: Request) {
  const { searchParams } = new URL(req.url);
  const conversationId = searchParams.get('conversationId');
  if (!conversationId) return json({ error: 'Missing conversationId' }, 400);

  try {
    await getMemoryClient().shortTerm.deleteConversation(conversationId);
    return json({ deleted: true }, 200);
  } catch (err) {
    console.error('[chat/route] Failed to delete NAMS conversation:', err);
    return json({ error: 'Failed to delete conversation from memory.' }, 500);
  }
}

export async function POST(req: Request) {
  // ── Parse & validate request body ─────────────────────────────────────────
  let body: { messages: UIMessage[]; sessionId?: string; userId?: string; conversationId?: string };
  try {
    body = await req.json();
  } catch {
    return json({ error: 'Invalid JSON in request body' }, 400);
  }

  if (!Array.isArray(body?.messages)) {
    return json({ error: '`messages` must be an array' }, 400);
  }

  const uiMessages: UIMessage[] = body.messages;
  const sessionId = body.sessionId ?? crypto.randomUUID();
  // Prefer the stable per-browser userId over the per-chat sessionId so NAMS can
  // correlate context across all conversations from the same person.
  const userId = body.userId ?? sessionId;
  const existingConversationId = body.conversationId ?? undefined;

  // ── Create / retrieve NAMS conversation ───────────────────────────────────
  let conversationId: string;
  try {
    conversationId = await ensureConversation(userId, existingConversationId);
  } catch (err) {
    console.error('[chat/route] Failed to create NAMS conversation:', err);
    return json({ error: 'Memory service unavailable. Please try again.' }, 503);
  }

  // ── Extract latest user message text ──────────────────────────────────────
  const lastUser = [...uiMessages].reverse().find(m => m.role === 'user');
  const userText = lastUser
    ? lastUser.parts
        .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
        .map(p => p.text)
        .join('')
    : '';

  // ── Retrieve three-tier context + semantic long-term matches ───────────────
  // We fetch context metadata for the UI badge, then use agentMemoryMiddleware
  // to inject this context into the model call automatically.
  let historyMsgs: HistoryMsg[] = [];
  let memoryCtxData = { semanticMatches: 0, reflections: 0, observations: 0, recentMessages: 0 };
  try {
    const ctx = await getMemoryClient().shortTerm.getContext(conversationId);

    const semanticMatches = userText
      ? await searchMemoryContext(conversationId, userText)
      : [];

    // Deduplicate semantic hits already in recentMessages
    const recentContents = new Set(ctx.recentMessages.map((m) => m.content));
    const uniqueMatches = semanticMatches.filter((c) => !recentContents.has(c));

    memoryCtxData = {
      semanticMatches: uniqueMatches.length,
      reflections: ctx.reflections.length,
      observations: ctx.observations.length,
      recentMessages: ctx.recentMessages.length,
    };

    // Build context messages: semantic + reflections + observations + recent history
    // recentMessages are stored newest-first — reverse to chronological order
    historyMsgs = [
      ...uniqueMatches.map((c) => ({ role: 'system' as const, content: `[relevant past context] ${c}` })),
      ...ctx.reflections.map(r  => ({ role: 'system' as const, content: `[reflection] ${r.content}` })),
      ...ctx.observations.map(o => ({ role: 'system' as const, content: `[observation] ${o.content}` })),
      ...[...ctx.recentMessages].reverse().map(m => ({ role: m.role as 'user' | 'assistant', content: m.content })),
    ];
  } catch (err) {
    console.warn('[chat/route] Could not load conversation context:', err);
  }

  // ── Detect first message ───────────────────────────────────────────────────
  const isFirstMessage =
    uiMessages.filter(m => m.role === 'user').length === 1 &&
    uiMessages.filter(m => m.role === 'assistant').length === 0;

  // ── Persist user message to NAMS before generation ────────────────────────
  if (userText) {
    getMemoryClient().shortTerm
      .addMessage(conversationId, 'user', userText)
      .catch(err => console.error('[chat/route] Failed to persist user message:', err));
  }

  // ── Stream ─────────────────────────────────────────────────────────────────
  try {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        // Stream memory context metadata so the UI can show the 🧠 badge
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        writer.write({ type: 'data-memory-context', data: memoryCtxData } as any);

        const titlePromise =
          isFirstMessage && userText
            ? generateTitle(userText).catch(() => null)
            : Promise.resolve(null);

        // Pass only the latest user message to the model.
        // historyMsgs (from NAMS) provides full conversation history —
        // this avoids duplicating the history the client also sends.
        const latestMsg = userText
          ? [{ role: 'user' as const, content: userText }]
          : [];

        const result = streamText({
          model: openai('gpt-4o-mini'),
          system: BASE_SYSTEM_PROMPT,
          messages: [...historyMsgs, ...latestMsg],
          onFinish: async ({ text }) => {
            if (text) {
              getMemoryClient().shortTerm
                .addMessage(conversationId, 'assistant', text)
                .catch(err =>
                  console.error('[chat/route] Failed to persist assistant message:', err),
                );
            }
          },
        });

        writer.merge(result.toUIMessageStream());

        const title = await titlePromise;
        if (title) {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          writer.write({ type: 'data-session-title', data: title, transient: true } as any);
        }
      },
      onError: (error) => {
        console.error('[chat/route] Stream error:', error);
        return 'Failed to generate a response. Please try again.';
      },
    });

    return createUIMessageStreamResponse({ stream });
  } catch (err) {
    console.error('[chat/route] createUIMessageStream failed:', err);
    return json({ error: 'Failed to generate a response. Please try again.' }, 500);
  }
}
