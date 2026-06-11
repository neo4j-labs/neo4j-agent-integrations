
import { getConversationReasoning } from '@/Chat/chat';

export const runtime = 'nodejs';

const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const conversationId = searchParams.get('conversationId');

  if (!conversationId) {
    return json({ error: 'Missing conversationId' }, 400);
  }

  console.log(`[reasoning/GET] Fetching trace for conversation: ${conversationId}`);

  try {
    const trace = await getConversationReasoning(conversationId);
    return json(trace, 200);
  } catch (err: unknown) {
    console.error('[reasoning/GET] Failed to fetch reasoning trace:', err);
    return json({ error: 'Failed to retrieve reasoning trace.' }, 500);
  }
}
