/**
 * GET /api/reasoning — reads the reasoning trace via @neo4j-labs/nams-ai-provider.
 *
 * Contract points:
 *  - userId is required; MEMORY_API_KEY must be configured
 *  - makeClient()/findExistingConversation() are called with {apiKey, workspaceId}
 *  - no existing conversation → { steps: [] }, not an error
 *  - client failures surface as 500, not an unhandled rejection
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const holder = vi.hoisted(() => ({
  makeClient: vi.fn(),
  findExistingConversation: vi.fn(),
}));

vi.mock('@neo4j-labs/nams-ai-provider', () => ({
  makeClient: holder.makeClient,
  findExistingConversation: holder.findExistingConversation,
}));

import { GET } from '../app/api/reasoning/route';

const req = (url: string) => new Request(url);

beforeEach(() => {
  vi.clearAllMocks();
  process.env.MEMORY_API_KEY = 'test-key';
  delete process.env.MEMORY_WORKSPACE_ID;
  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('GET /api/reasoning', () => {
  it('returns 400 when userId is missing', async () => {
    const res = await GET(req('http://localhost/api/reasoning'));

    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({ error: 'Missing userId' });
    expect(holder.makeClient).not.toHaveBeenCalled();
  });

  it('returns 503 when MEMORY_API_KEY is not set', async () => {
    delete process.env.MEMORY_API_KEY;

    const res = await GET(req('http://localhost/api/reasoning?userId=u1'));

    expect(res.status).toBe(503);
    expect(holder.makeClient).not.toHaveBeenCalled();
  });

  it('returns an empty steps list when no conversation exists yet', async () => {
    holder.makeClient.mockReturnValue({ reasoning: { listSteps: vi.fn() } });
    holder.findExistingConversation.mockResolvedValue(null);

    const res = await GET(req('http://localhost/api/reasoning?userId=u1'));

    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ steps: [] });
  });

  it('passes apiKey/workspaceId through and returns listSteps() output', async () => {
    process.env.MEMORY_WORKSPACE_ID = 'ws-1';
    const listSteps = vi.fn().mockResolvedValue([{ reasoning: 'looked up user prefs' }]);
    holder.makeClient.mockReturnValue({ reasoning: { listSteps } });
    holder.findExistingConversation.mockResolvedValue('conv-42');

    const res = await GET(req('http://localhost/api/reasoning?userId=u1&conversationId=conv-42'));

    expect(holder.makeClient).toHaveBeenCalledWith({ apiKey: 'test-key', workspaceId: 'ws-1' });
    expect(holder.findExistingConversation).toHaveBeenCalledWith(
      expect.anything(),
      { apiKey: 'test-key', workspaceId: 'ws-1' },
      { userId: 'u1', conversationId: 'conv-42' },
    );
    expect(listSteps).toHaveBeenCalledWith('conv-42');
    expect(await res.json()).toEqual({ steps: [{ reasoning: 'looked up user prefs' }] });
  });

  it('returns 500 when the NAMS client throws', async () => {
    holder.makeClient.mockImplementation(() => {
      throw new Error('boom');
    });

    const res = await GET(req('http://localhost/api/reasoning?userId=u1'));

    expect(res.status).toBe(500);
    expect(await res.json()).toEqual({ error: 'Failed to retrieve reasoning trace.' });
  });
});
