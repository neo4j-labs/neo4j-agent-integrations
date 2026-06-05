
import { openai } from '@ai-sdk/openai';
import {
  streamText,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
  type UIMessage,
} from 'ai';
import {
  ensureConversation,
  searchMemoryContext,
  searchUserMemoryContext,
  searchPreviousConversations,
  getConversationContext,
  addMessage,
  deleteConversation,
  runWithMcpTracker,
  getNeo4jMcpTools,
  type McpToolRecord,
} from '@/Chat/chat';
import { BASE_SYSTEM_PROMPT } from '@/lib/constants';
import { generateTitle } from '@/lib/title';
import type { HistoryMsg } from '@/lib/types';

export const runtime = 'nodejs';

const MAX_TOOL_STEPS = 5;

const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

// ── GET conversation history
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('sessionId');
  const existingConversationId = searchParams.get('conversationId') ?? undefined;

  if (!sessionId) {
    return json({ error: 'Missing sessionId' }, 400);
  }

  console.log(`\n${'─'.repeat(60)}`);
  console.log(`[chat/GET] ① Loading history | session: ${sessionId} | existingConv: ${existingConversationId ?? 'none'}`);

  let conversationId: string;
  try {
    conversationId = await ensureConversation(sessionId, existingConversationId);
  } catch {
    console.warn('[chat/GET] Could not resolve conversation — returning empty history');
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

    console.log(`[chat/GET] ② Returning ${uiMessages.length} stored message(s) to UI`);
    return json({ messages: uiMessages, conversationId }, 200);
  } catch {
    console.warn(`[chat/GET] Failed to load context for ${conversationId} — returning empty history`);
    return json({ messages: [], conversationId }, 200);
  }
}

// ── DELETE conversation

export async function DELETE(req: Request) {
  const { searchParams } = new URL(req.url);
  const conversationId = searchParams.get('conversationId');

  if (!conversationId) {
    return json({ error: 'Missing conversationId' }, 400);
  }

  try {
    await deleteConversation(conversationId);
    return json({ deleted: true }, 200);
  } catch (err: unknown) {
    console.error('[chat/route] Failed to delete conversation:', err);
    const errMsg = String(err);
    if (errMsg.includes('404') || errMsg.includes('not found')) {
      return json({ deleted: true, note: 'Conversation was not found' }, 200);
    }
    return json({ error: 'Failed to delete conversation from memory.' }, 500);
  }
}

// ── POST chat turn

export async function POST(req: Request) {
  let body: { messages: UIMessage[]; sessionId?: string; userId?: string; conversationId?: string; previousConversationIds?: string[] };
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
  const previousConversationIds: string[] = body.previousConversationIds ?? [];
  const lastUser = [...uiMessages].reverse().find((m) => m.role === 'user');
  const userText = lastUser
    ? lastUser.parts
      .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
      .map((p) => p.text)
      .join('')
    : '';

  //1: create conversation
  console.log(`\n${'═'.repeat(60)}`);
  console.log(`[chat/POST] ① Incoming query: "${userText}"`);
  console.log(`[chat/POST]   session: ${sessionId} | existingConv: ${existingConversationId ?? 'none'} | prevConvs: ${previousConversationIds.length}`);

  let conversationId: string;
  try {
    conversationId = await ensureConversation(userId, existingConversationId);
    console.log(`[chat/POST]   Conversation resolved: ${conversationId}`);
  } catch (err: unknown) {
    console.error('[chat/POST] Failed to resolve conversation:', err);
    return json({ error: 'Memory service unavailable. Please try again.' }, 503);
  }

  //2: extract UI message history
  const uiConversationMsgs = uiMessages
    .filter((m) => m.role === 'user' || m.role === 'assistant')
    .map((m) => ({
      role: m.role as 'user' | 'assistant',
      content: m.parts
        .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
        .map((p) => p.text)
        .join(''),
    }))
    .filter((m) => m.content);

  console.log(`[chat/POST] ② UI carries ${uiConversationMsgs.length} message(s) in this request`);

  //3: retrieve memory context
  console.log(`[chat/POST] ③ Retrieving memory context…`);

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
      // 3a — stored conversation context (reflections, observations, recent messages)
      const ctx = await getConversationContext(conversationId);

      // 3b — semantic search in current conversation
      const conversationMatches = userText
        ? await searchMemoryContext(conversationId, userText)
        : [];

      // 3c — semantic search in explicitly provided previous conversations
      const prevMatches =
        userText && conversationMatches.length === 0 && previousConversationIds.length > 0
          ? await searchPreviousConversations(previousConversationIds, userText)
          : [];

      // 3d — user-level search across all their conversations
      const userMatches =
        userText && conversationMatches.length === 0 && prevMatches.length === 0
          ? await searchUserMemoryContext(userId, userText)
          : [];

      return { ctx, conversationMatches, prevMatches, userMatches };
    });

    const { ctx, conversationMatches, prevMatches, userMatches } = result;
    const uiContents = new Set(uiConversationMsgs.map((m) => m.content));
    const uniqueConvMatches = conversationMatches.filter((c) => !uiContents.has(c));
    const uniquePrevMatches = prevMatches.filter(
      (c) => !uiContents.has(c) && !uniqueConvMatches.includes(c),
    );
    const uniqueUserMatches = userMatches.filter(
      (c) => !uiContents.has(c) && !uniqueConvMatches.includes(c) && !uniquePrevMatches.includes(c),
    );

    // Recent messages stored in memory but not yet in the UI (e.g. after page refresh)
    const recentFromMemory = ctx.recentMessages
      .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.content && !uiContents.has(m.content))
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }));

    memoryCtxData = {
      semanticMatches: uniqueConvMatches.length + uniquePrevMatches.length + uniqueUserMatches.length,
      reflections: ctx.reflections.length,
      observations: ctx.observations.length,
      recentMessages: uiConversationMsgs.length + recentFromMemory.length,
      mcpTools,
    };

    historyMsgs = [
      ...recentFromMemory,
      ...uniqueConvMatches.map((c) => ({ role: 'system' as const, content: `[relevant past context] ${c}` })),
      ...uniquePrevMatches.map((c) => ({ role: 'system' as const, content: `[cross-session memory] ${c}` })),
      ...uniqueUserMatches.map((c) => ({ role: 'system' as const, content: `[cross-session memory] ${c}` })),
      ...ctx.reflections.map((r) => ({ role: 'system' as const, content: `[reflection] ${r.content}` })),
      ...ctx.observations.map((o) => ({ role: 'system' as const, content: `[observation] ${o.content}` })),
    ];

    //3 summary
    console.log(`[chat/POST] ③ Memory retrieval summary:`);
    console.log(`[chat/POST]   • recent-from-memory (not in UI): ${recentFromMemory.length}`);
    console.log(`[chat/POST]   • semantic hits (current conv):    ${uniqueConvMatches.length}`);
    console.log(`[chat/POST]   • semantic hits (prev convs):      ${uniquePrevMatches.length}`);
    console.log(`[chat/POST]   • semantic hits (user-level):      ${uniqueUserMatches.length}`);
    console.log(`[chat/POST]   • reflections:                     ${ctx.reflections.length}`);
    console.log(`[chat/POST]   • observations:                    ${ctx.observations.length}`);
    console.log(`[chat/POST]   → Total context msgs sent to LLM:  ${historyMsgs.length + uiConversationMsgs.length}`);

  } catch (err: unknown) {
    console.warn('[chat/POST] ③ Could not load memory context (continuing without it):', err);
  }

  //4: store user message (fire-and-forget)
  if (userText) {
    console.log(`[chat/POST] ④ Storing user message to memory (async)…`);
    addMessage(conversationId, 'user', userText).catch((err: unknown) =>
      console.error('[chat/POST] ④ Failed to persist user message:', err),
    );
  }

  const isFirstMessage =
    uiMessages.filter((m) => m.role === 'user').length === 1 &&
    uiMessages.filter((m) => m.role === 'assistant').length === 0;

  //5: run agent loop
  try {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        writer.write({ type: 'data-memory-context', data: memoryCtxData } as any);

        const titlePromise =
          isFirstMessage && userText
            ? generateTitle(userText).catch(() => null)
            : Promise.resolve(null);

        let neo4jTools = {};
        try {
          neo4jTools = await getNeo4jMcpTools();
          console.log(`[chat/POST] ⑤ Tools loaded: ${Object.keys(neo4jTools).join(', ') || 'none'}`);
        } catch (err) {
          console.warn('[chat/POST] ⑤ Could not load Neo4j MCP tools:', err);
        }

        const semanticHits =
          memoryCtxData.semanticMatches + memoryCtxData.reflections + memoryCtxData.observations;
        const hasStrongMemory = semanticHits >= 1;

        const systemContextItems = historyMsgs
          .filter((m) => m.role === 'system')
          .map((m) => m.content);

        const memoryContextStr =
          systemContextItems.length > 0
            ? `\n\n[UserContext]: ${systemContextItems.join(' | ')}\n\nINSTRUCTION: ${
                hasStrongMemory
                  ? 'STRONGLY PREFER using [UserContext] to answer. Only call tools if the user explicitly asks for a live query, or if the context is clearly outdated or contradicted.'
                  : 'ALWAYS check [UserContext] AND the conversation history before calling any tool. If the answer or sufficient context is present, use it directly without a DB query. Only call tools when the answer genuinely requires new data not present in the context or history.'
              }`
            : '\n\nINSTRUCTION: ALWAYS check the conversation history before calling any tool. If the answer or sufficient context is already in the conversation, use it directly without a DB query.';

        console.log(
          `[chat/POST] ⑤ Agent loop starting | model: gpt-5.4-mini | maxSteps: ${MAX_TOOL_STEPS} | hasStrongMemory: ${hasStrongMemory}`,
        );

        const result = streamText({
          model: openai('gpt-5.4-mini'),
          system: `${BASE_SYSTEM_PROMPT}${memoryContextStr}`,
          messages: [...historyMsgs, ...uiConversationMsgs],
          tools: neo4jTools,
          stopWhen: stepCountIs(MAX_TOOL_STEPS),
          onFinish: async ({ text, steps }) => {
            console.log(`[chat/POST] ⑥ Agent finished in ${steps.length} step(s)`);
            if (text) {
              //6: store assistant response
              console.log(`[chat/POST] ⑥ Storing assistant response to memory…`);
              await addMessage(conversationId, 'assistant', text).catch((err: unknown) =>
                console.error('[chat/POST] ⑥ Failed to persist assistant message:', err),
              );
              console.log(`[chat/POST] ⑥ ✓ Assistant response stored. Memory flow complete.`);
            } else {
              console.log(`[chat/POST] ⑥ No text to store (tool-only response or empty).`);
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
        console.error('[chat/POST] Stream error:', error);
        return 'Failed to generate a response. Please try again.';
      },
    });

    return createUIMessageStreamResponse({ stream });
  } catch (err: unknown) {
    console.error('[chat/POST] createUIMessageStream failed:', err);
    return json({ error: 'Failed to generate a response. Please try again.' }, 500);
  }
}
