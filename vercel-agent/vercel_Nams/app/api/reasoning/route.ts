import { findExistingConversation, type NamsMemoryOptions } from '@/lib/nams-memory-provider';

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

  const memoryOptions: NamsMemoryOptions = {
    apiKey:      process.env.MEMORY_API_KEY ?? '',
    userId,
    conversationId,
    workspaceId: process.env.MEMORY_WORKSPACE_ID,
  };

  if (!memoryOptions.apiKey) return json({ error: 'MEMORY_API_KEY not set' }, 503);

  try {
    const result = await findExistingConversation(memoryOptions);
    if (!result) return json({ steps: [] }, 200);
    const steps = await result.client.reasoning.listSteps(result.convId);
    return json({ steps }, 200);
  } catch (err) {
    console.error('[reasoning/GET] Failed to fetch reasoning trace:', err);
    return json({ error: 'Failed to retrieve reasoning trace.' }, 500);
  }
}
