/** guardTools: slow tool calls stop after 30s, huge results are cut short. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { guardTools } from '../lib/neo4j-mcp';

afterEach(() => vi.useRealTimers());

describe('guardTools', () => {
  it('returns an error result instead of waiting on a slow tool', async () => {
    vi.useFakeTimers();
    const tools = guardTools({ 'read-cypher': { execute: () => new Promise(() => {}) } });

    const pending = (tools['read-cypher'] as any).execute({ query: 'MATCH (n) RETURN n' });
    await vi.advanceTimersByTimeAsync(30_000);

    await expect(pending).resolves.toMatchObject({
      isError: true,
      content: [{ type: 'text', text: expect.stringContaining('took longer than 30s') }],
    });
  });

  it('cuts a huge text result short and says how to get the rest', async () => {
    const big = 'x'.repeat(60_000);
    const tools = guardTools({ 'read-cypher': { execute: async () => ({ content: [{ type: 'text', text: big }] }) } });

    const out = await (tools['read-cypher'] as any).execute({});

    expect(out.content[0].text.length).toBeLessThan(big.length);
    expect(out.content[0].text).toContain('Add a LIMIT clause');
  });

  it('passes small results and tools without execute through unchanged', async () => {
    const schemaOnly = { description: 'no execute' };
    const tools = guardTools({ a: { execute: async () => 'ok' }, b: schemaOnly });

    expect(await (tools.a as any).execute({})).toBe('ok');
    expect(tools.b).toBe(schemaOnly);
  });
});
