
import { openai } from '@ai-sdk/openai';
import { streamText, convertToModelMessages, type UIMessage } from 'ai';
import { createSessionId, storeMessage, getRecentMessages } from '@/Chat/chat';

export const runtime = 'nodejs';

const BASE_SYSTEM_PROMPT = `\
You are a helpful Neo4j knowledge-graph analyst. \
Answer questions clearly and concisely. \
When you are unsure, say so rather than guessing.`;

export async function POST(req: Request) {
  const body = await req.json() as {
    messages: UIMessage[];
    sessionId?: string;
  };

  const sessionId = createSessionId(body.sessionId);
  const uiMessages: UIMessage[] = body.messages ?? [];
  const storedHistory = await getRecentMessages(sessionId);

  const historyModelMsgs =
    storedHistory.length > 0 && uiMessages.length === 1
      ? storedHistory.map((m) => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }))
      : [];

  const clientModelMsgs = await convertToModelMessages(uiMessages);
  const allModelMsgs = [...historyModelMsgs, ...clientModelMsgs];
  const result = streamText({
    model: openai('gpt-4o-mini'),
    system: BASE_SYSTEM_PROMPT,
    messages: allModelMsgs,
    onFinish: async ({ text }) => {
      const lastUser = uiMessages.findLast((m) => m.role === 'user');
      const userText = lastUser
        ? lastUser.parts
          .filter(
            (p): p is { type: 'text'; text: string } => p.type === 'text'
          )
          .map((p) => p.text)
          .join('')
        : '';

      if (userText) await storeMessage(sessionId, 'user', userText);
      if (text) await storeMessage(sessionId, 'assistant', text);
    },
  });
  return result.toUIMessageStreamResponse();
}
