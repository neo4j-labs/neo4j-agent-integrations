/** GET /api/memory: the per-turn snapshot of what NAMS holds, in every mode. */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const holder = vi.hoisted(() => ({
  makeClient: vi.fn(),
  findExistingConversation: vi.fn(),
  getContext: vi.fn(),
  searchEntities: vi.fn(),
  listEntities: vi.fn(),
  getTraceByConversation: vi.fn(),
}));

vi.mock('@neo4j-labs/nams-ai-provider', () => ({
  makeClient: holder.makeClient,
  findExistingConversation: holder.findExistingConversation,
}));

import { GET } from '../app/api/memory/route';

const get = (query: string) => GET(new Request(`http://localhost/api/memory?${query}`));

beforeEach(() => {
  vi.clearAllMocks();
  process.env.NAMS_API_KEY = 'test-key';
  delete process.env.MEMORY_WORKSPACE_ID;
  vi.spyOn(console, 'error').mockImplementation(() => {});

  holder.makeClient.mockReturnValue({
    shortTerm: { getContext: holder.getContext },
    longTerm: { searchEntities: holder.searchEntities, listEntities: holder.listEntities },
    reasoning: { getTraceByConversation: holder.getTraceByConversation },
  });
  holder.findExistingConversation.mockResolvedValue('conv-1');
  holder.getContext.mockResolvedValue({ recentMessages: [], observations: [], reflections: [] });
  holder.searchEntities.mockResolvedValue([]);
  holder.listEntities.mockResolvedValue([]);
  holder.getTraceByConversation.mockResolvedValue({ conversationId: 'conv-1', steps: [], toolCalls: [] });
});

describe('GET /api/memory', () => {
  it('returns 400 without a userId', async () => {
    expect((await get('q=x')).status).toBe(400);
  });

  it('returns 503 without NAMS_API_KEY', async () => {
    delete process.env.NAMS_API_KEY;
    expect((await get('userId=u1')).status).toBe(503);
  });

  it('puts recent messages in chat order and leaves out tool records', async () => {
    // Hosted NAMS: newest first, the assistant reply before its question on a shared timestamp.
    holder.getContext.mockResolvedValue({
      recentMessages: [
        { role: 'assistant', content: 'Hi Alex', timestamp: '2026-11-12T03:59:13Z', metadata: {} },
        { role: 'user', content: 'I am Alex', timestamp: '2026-11-12T03:59:13Z', metadata: {} },
        { role: 'assistant', content: '[tool-call] x', timestamp: '2026-11-12T03:58:00Z', metadata: { namsKind: 'tool-call' } },
        { role: 'user', content: 'hello', timestamp: '2026-11-12T03:56:09Z', metadata: {} },
      ],
      observations: [{ content: 'Alex likes graphs' }],
      reflections: [{ content: '' }],
    });

    const body = await (await get('userId=u1')).json();

    expect(holder.findExistingConversation).toHaveBeenCalledWith(
      expect.anything(), { apiKey: 'test-key', workspaceId: undefined }, { userId: 'u1' },
    );
    expect(body.items.recent.map((m: any) => m.content)).toEqual(['hello', 'I am Alex', 'Hi Alex']);
    expect(body.counts).toMatchObject({ recent: 3, observations: 1, insights: 0 });
  });

  it('searches entities with the question, or lists them when there is none', async () => {
    holder.searchEntities.mockResolvedValue([{ name: 'Neo4j', type: 'Organization', description: 'a graph db', userId: 'u1' }]);

    const searched = await (await get('userId=u1&q=neo4j')).json();
    expect(holder.searchEntities).toHaveBeenCalledWith('neo4j', { limit: 8, userId: 'u1' });
    expect(searched.items.entities).toEqual([{ content: 'Neo4j — a graph db', label: 'Organization' }]);

    await get('userId=u1');
    expect(holder.listEntities).toHaveBeenCalledWith({ limit: 200 });
  });

  it("shows only this user's entities, never other users' or shared ones", async () => {
    const entities = [
      { name: 'Mine', type: 'Concept', userId: 'u1' },
      { name: 'Theirs', type: 'Person', userId: 'u2' },
      { name: 'Shared', type: 'Concept' },
    ];
    holder.searchEntities.mockResolvedValue(entities);
    holder.listEntities.mockResolvedValue(entities);

    for (const q of ['userId=u1&q=me', 'userId=u1']) {
      const body = await (await get(q)).json();
      expect(body.items.entities.map((e: { content: string }) => e.content)).toEqual(['Mine']);
    }
  });

  it('labels reasoning steps with their action and result', async () => {
    holder.getTraceByConversation.mockResolvedValue({
      steps: [{ reasoning: 'check the schema', actionTaken: 'get-schema', result: '1 tool call(s)' }],
      toolCalls: [],
    });

    const body = await (await get('userId=u1')).json();

    expect(body.items.reasoning).toEqual([{ content: 'check the schema', label: 'get-schema · 1 tool call(s)' }]);
  });

  it('still answers when the trace endpoint fails', async () => {
    holder.getTraceByConversation.mockRejectedValue(new Error('boom'));

    const res = await get('userId=u1');

    expect(res.status).toBe(200);
    expect((await res.json()).counts.reasoning).toBe(0);
  });

  it('skips conversation reads for a user with no conversation yet', async () => {
    holder.findExistingConversation.mockResolvedValue(null);

    const body = await (await get('userId=new')).json();

    expect(holder.getContext).not.toHaveBeenCalled();
    expect(holder.getTraceByConversation).not.toHaveBeenCalled();
    expect(body.counts.recent).toBe(0);
  });

  it('returns 502 when NAMS fails', async () => {
    holder.listEntities.mockRejectedValue(new Error('down'));

    const res = await get('userId=u1');

    expect(res.status).toBe(502);
    expect((await res.json()).error).toContain('down');
  });
});
