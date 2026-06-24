import { makeClient, findExistingConversation } from '@/lib/nams/client';

export const runtime = 'nodejs';

const json = (data: unknown, status: number) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const userId         = searchParams.get('userId');
  const conversationId = searchParams.get('conversationId') ?? undefined;

  if (!userId) return json({ error: 'Missing userId' }, 400);

  const apiKey = process.env.MEMORY_API_KEY ?? '';
  if (!apiKey) return json({ error: 'MEMORY_API_KEY not set' }, 503);

  const config = {
    apiKey,
    workspaceId: process.env.MEMORY_WORKSPACE_ID,
  };
  const scope = { userId, conversationId };

  try {
    const client = makeClient(config);
    const convId = await findExistingConversation(client, config, scope);

    if (!convId) {
      console.log(`[reasoning/GET] No conversation found for userId=${userId}`);
      return json({ steps: [] }, 200);
    }

    console.log(`[reasoning/GET] Listing reasoning steps for convId=${convId} userId=${userId}`);
    const steps = await client.reasoning.listSteps(convId);
    console.log(`[reasoning/GET] Returning ${steps.length} steps`);
    return json({ steps }, 200);
  } catch (err) {
    console.error('[reasoning/GET] Failed to fetch reasoning trace:', err);
    return json({ error: 'Failed to retrieve reasoning trace.' }, 500);
  }
}
