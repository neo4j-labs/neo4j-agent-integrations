
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

// Configuration & Constants
export const runtime = 'nodejs';

const MAX_CONVERSATION_SCAN = 20;
const MAX_TOOL_STEPS = 5;

// Utility Functions 
const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const sessionId = searchParams.get('sessionId');
  const existingConversationId = searchParams.get('conversationId') ?? undefined;

  if (!sessionId) {
    return json({ error: 'Missing sessionId' }, 400);
  }

  // Ensure conversation exists
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

  // Extract Request Parameters
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

  let conversationId: string;
  try {
    conversationId = await ensureConversation(userId, existingConversationId);
  } catch (err: unknown) {
    console.error('[chat/route] Failed to create conversation:', err);
    return json({ error: 'Memory service unavailable. Please try again.' }, 503);
  }

  console.log(`[chat/route] User query: "${userText}"\n...Retrieving relevant memory context...`);
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
      const conversationMatches = userText
        ? await searchMemoryContext(conversationId, userText)
        : [];
      
      const isNewConversation = ctx.recentMessages.length < 3;
      const prevMatches = isNewConversation && userText && previousConversationIds.length > 0
        ? await searchPreviousConversations(previousConversationIds, userText)
        : [];
      
      const userMatches = isNewConversation && userText && prevMatches.length === 0
        ? await searchUserMemoryContext(userId, userText)
        : [];
      
      return { ctx, conversationMatches, prevMatches, userMatches };
    });

    const { ctx, conversationMatches, prevMatches, userMatches } = result;
    const recentContents = new Set(ctx.recentMessages.map((m) => m.content));
    const uniqueConvMatches = conversationMatches.filter((c) => !recentContents.has(c));
    const uniquePrevMatches = prevMatches.filter(
      (c) => !recentContents.has(c) && !uniqueConvMatches.includes(c)
    );
    const uniqueUserMatches = userMatches.filter(
      (c) => !recentContents.has(c) && !uniqueConvMatches.includes(c) && !uniquePrevMatches.includes(c)
    );

    memoryCtxData = {
      semanticMatches: uniqueConvMatches.length + uniquePrevMatches.length + uniqueUserMatches.length,
      reflections: ctx.reflections.length,
      observations: ctx.observations.length,
      recentMessages: ctx.recentMessages.length,
      mcpTools
    };

    historyMsgs = [
      ...uniqueConvMatches.map((c) => ({ role: 'system' as const, content: `[relevant past context] ${c}` })),
      ...uniquePrevMatches.map((c) => ({ role: 'system' as const, content: `[cross-session memory] ${c}` })),
      ...uniqueUserMatches.map((c) => ({ role: 'system' as const, content: `[cross-session memory] ${c}` })),
      ...ctx.reflections.map((r) => ({ role: 'system' as const, content: `[reflection] ${r.content}` })),
      ...ctx.observations.map((o) => ({ role: 'system' as const, content: `[observation] ${o.content}` })),
      ...[...ctx.recentMessages].reverse().slice(-8).map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
    ];

    console.log(
      `[Memory Retrieved] ${uniqueConvMatches.length} conversation matches, ` +
      `${uniquePrevMatches.length} previous-conversation matches, ` +
      `${uniqueUserMatches.length} user-level matches, ` +
      `${ctx.reflections.length} reflections, ${ctx.observations.length} observations`,
    );
  } catch (err: unknown) {
    console.warn('[chat/route] Could not load conversation context:', err);
  }

  if (userText) {
    addMessage(conversationId, 'user', userText).catch((err: unknown) =>
      console.error('[chat/route] Failed to persist user message:', err),
    );
  }

  const isFirstMessage =
    uiMessages.filter((m) => m.role === 'user').length === 1 &&
    uiMessages.filter((m) => m.role === 'assistant').length === 0;

  //Execute Agent Loop
  try {
    const stream = createUIMessageStream({
      execute: async ({ writer }) => {
        writer.write({ type: 'data-memory-context', data: memoryCtxData } as any);

        // Generate title for first message (non-blocking)
        const titlePromise =
          isFirstMessage && userText
            ? generateTitle(userText).catch(() => null)
            : Promise.resolve(null);
        const latestMsg = userText ? [{ role: 'user' as const, content: userText }] : [];

        let neo4jTools = {};
        try {
          neo4jTools = await getNeo4jMcpTools();
          console.log(`[Tools Loaded] Available: ${Object.keys(neo4jTools).join(', ')}`);
        } catch (err) {
          console.warn('[chat/route] Could not load Neo4j MCP tools:', err);
        }

        const totalMemoryMatches = memoryCtxData.semanticMatches + memoryCtxData.recentMessages;
        const hasStrongMemory = memoryCtxData.semanticMatches >= 2 || totalMemoryMatches >= 3;
        
        const memoryContextStr =
          totalMemoryMatches > 0
            ? `\n\n[UserContext]: ${historyMsgs
                .filter((m) => m.role === 'system')
                .map((m) => m.content)
                .join(' | ')}\n\nINSTRUCTION: ${
                  hasStrongMemory
                    ? 'STRONGLY PREFER using [UserContext] to answer. The user context contains relevant information. Only call tools if the user explicitly asks you to (e.g., "query the database", "find in graph"), or if context is clearly outdated/contradicted.'
                    : 'When [UserContext] directly answers the user\'s question, reuse it. Note that [cross-session memory] entries come from previous conversations. If the context is incomplete, outdated, or unrelated, call tools or use other context.'
                }`
            : '';

        const enhancedSystemPrompt = `${BASE_SYSTEM_PROMPT}${memoryContextStr}`;
        console.log(
          `\n[Executing Agent Loop] Model: gpt-4o-mini | Max steps: ${MAX_TOOL_STEPS}\n...Waiting for agentic loop...\n`,
        );

        const result = streamText({
          model: openai('gpt-4o-mini'),
          system: enhancedSystemPrompt,
          messages: [...historyMsgs, ...latestMsg],
          tools: neo4jTools,
          stopWhen: stepCountIs(MAX_TOOL_STEPS),
          onFinish: async ({ text, steps }) => {
            // Persist Assistant Response to Memory
            if (text) {
              await addMessage(conversationId, 'assistant', text).catch((err: unknown) =>
                console.error('[chat/route] Failed to persist assistant message:', err),
              );
              console.log(
                `[Agent Complete] Generated response in ${steps.length} step(s). Message persisted to Agent Memory.`,
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
