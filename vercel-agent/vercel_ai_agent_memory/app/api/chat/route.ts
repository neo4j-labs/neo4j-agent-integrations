
import { openai } from '@ai-sdk/openai';
import {
  streamText,
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from 'ai';
import {
  ensureConversation,
  searchMemoryContext,
  getConversationContext,
  addMessage,
  deleteConversation,
  runWithMcpTracker,
  type McpToolRecord,
} from '@/Chat/chat';
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
    const ctx = await getConversationContext(conversationId);
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
    await deleteConversation(conversationId);
    return json({ deleted: true }, 200);
  } catch (err: unknown) {
    console.error('[chat/route] Failed to delete conversation:', err);
    return json({ error: 'Failed to delete conversation from memory.' }, 500);
  }
}

export async function POST(req: Request) {
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
  const userId = body.userId ?? sessionId;
  const existingConversationId = body.conversationId ?? undefined;

  let conversationId: string;
  try {
    conversationId = await ensureConversation(userId, existingConversationId);
  } catch (err: unknown) {
    console.error('[chat/route] Failed to create conversation:', err);
    return json({ error: 'Memory service unavailable. Please try again.' }, 503);
  }

  const lastUser = [...uiMessages].reverse().find((m) => m.role === 'user');
  const userText = lastUser
    ? lastUser.parts
        .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
        .map((p) => p.text)
        .join('')
    : '';

  let historyMsgs: HistoryMsg[] = [];
  let memoryCtxData: {
    semanticMatches: number;
    reflections: number;
    observations: number;
    recentMessages: number;
    mcpTools: McpToolRecord[];
  } = { semanticMatches: 0, reflections: 0, observations: 0, recentMessages: 0, mcpTools: [] };

  try {
    const { result, mcpTools } = await runWithMcpTracker(async () => {
      const ctx = await getConversationContext(conversationId);
      const semanticMatches = userText
        ? await searchMemoryContext(conversationId, userText)
        : [];
      return { ctx, semanticMatches };
    });

    const { ctx, semanticMatches } = result;
    const recentContents = new Set(ctx.recentMessages.map((m) => m.content));
    const uniqueMatches = semanticMatches.filter((c) => !recentContents.has(c));

    memoryCtxData = {
      semanticMatches: uniqueMatches.length,
      reflections: ctx.reflections.length,
      observations: ctx.observations.length,
      recentMessages: ctx.recentMessages.length,
      mcpTools,
    };
    historyMsgs = [
      ...uniqueMatches.map((c) => ({ role: 'system' as const, content: `[relevant past context] ${c}` })),
      ...ctx.reflections.map((r) => ({ role: 'system' as const, content: `[reflection] ${r.content}` })),
      ...ctx.observations.map((o) => ({ role: 'system' as const, content: `[observation] ${o.content}` })),
      ...[...ctx.recentMessages].reverse().map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
    ];
  } catch (err: unknown) {
    console.warn('[chat/route] Could not load conversation context:', err);
  }

  const isFirstMessage =
    uiMessages.filter((m) => m.role === 'user').length === 1 &&
    uiMessages.filter((m) => m.role === 'assistant').length === 0;

  if (userText) {
    addMessage(conversationId, 'user', userText).catch((err: unknown) =>
      console.error('[chat/route] Failed to persist user message:', err),
    );
  }

  try {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        writer.write({ type: 'data-memory-context', data: memoryCtxData } as any);

        const titlePromise =
          isFirstMessage && userText
            ? generateTitle(userText).catch(() => null)
            : Promise.resolve(null);
        const latestMsg = userText ? [{ role: 'user' as const, content: userText }] : [];

        const result = streamText({
          model: openai('gpt-4o-mini'),
          system: BASE_SYSTEM_PROMPT,
          messages: [...historyMsgs, ...latestMsg],
          onFinish: async ({ text }) => {
            if (text) {
              addMessage(conversationId, 'assistant', text).catch((err: unknown) =>
                console.error('[chat/route] Failed to persist assistant message:', err),
              );
            }
          },
        });

        writer.merge(result.toUIMessageStream());

        const title = await titlePromise;
        if (title) {
          writer.write({ type: 'data-session-title', data: title, transient: true } as any);
        }
      },
      onError: (error) => {
        console.error('[chat/route] Stream error:', error);
        return 'Failed to generate a response. Please try again.';
      },
    });

    return createUIMessageStreamResponse({ stream });
  } catch (err: unknown) {
    console.error('[chat/route] createUIMessageStream failed:', err);
    return json({ error: 'Failed to generate a response. Please try again.' }, 500);
  }
}
