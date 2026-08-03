/**
 * POST /api/chat — wires @neo4j-labs/nams-ai-provider into ToolLoopAgent.
 *
 * Contract points:
 *  - MEMORY_API_KEY is required; invalid JSON bodies are rejected
 *  - NAMS_MODE=provider (default): createNamsProvider(...).languageModel() wraps
 *    the model transparently; no NAMS tools are attached
 *  - NAMS_MODE=middleware: createNams().wrap(model, scope) wraps the base model
 *    the same way; MCP tools (if configured) connect directly, same as provider mode
 *  - NAMS_MODE=tools: the base model is left unwrapped; createNams().toolsWithMcp()
 *    supplies query_memory/store_memory (+ MCP tools) to the agent
 *  - a failed MCP connection in tools mode falls back to NAMS-only tools
 *  - onFinish persists the step trace via makeClient()/resolveConversation()
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const holder = vi.hoisted(() => ({
  agentCtorArgs: [] as any[],
  executeFns: [] as any[],
  finalText: 'answer',
  finalFinishReason: 'stop',
  createNamsProvider: vi.fn(),
  createNams: vi.fn(),
  languageModel: vi.fn(),
  wrap: vi.fn(),
  toolsWithMcp: vi.fn(),
  makeClient: vi.fn(),
  resolveConversation: vi.fn(),
  enforceQueryMemory: vi.fn(() => ({ __prepareStep: true })),
  getNeo4jMcpTools: vi.fn(),
  getNamsMcpConfig: vi.fn(),
  isMcpConfigured: vi.fn(),
  explainMcpError: vi.fn(async (err: any) => err?.message ?? String(err)),
}));

vi.mock('@ai-sdk/openai', () => ({
  openai: vi.fn((modelId: string) => ({ __brand: 'openai-model', modelId })),
}));

vi.mock('ai', () => ({
  ToolLoopAgent: vi.fn().mockImplementation(function (this: any, args: any) {
    holder.agentCtorArgs.push(args);
    this.stream = vi.fn().mockResolvedValue({
      stream: new ReadableStream(),
      text: Promise.resolve(holder.finalText),
      finishReason: Promise.resolve(holder.finalFinishReason),
    });
  }),
  createUIMessageStream: vi.fn(({ execute }: any) => {
    holder.executeFns.push(execute);
    return { __execute: execute };
  }),
  createUIMessageStreamResponse: vi.fn(() => new Response(null, { status: 200 })),
  stepCountIs: vi.fn((n: number) => ({ __stepCountIs: n })),
  toUIMessageStream: vi.fn(({ stream }: any) => stream),
}));

vi.mock('@neo4j-labs/nams-ai-provider', () => ({
  createNamsProvider: holder.createNamsProvider,
  createNams: holder.createNams,
  makeClient: holder.makeClient,
  resolveConversation: holder.resolveConversation,
  enforceQueryMemory: holder.enforceQueryMemory,
}));

vi.mock('@/lib/neo4j-mcp', () => ({
  getNeo4jMcpTools: holder.getNeo4jMcpTools,
  getNamsMcpConfig: holder.getNamsMcpConfig,
  isMcpConfigured: holder.isMcpConfigured,
  explainMcpError: holder.explainMcpError,
}));

import { POST } from '../app/api/chat/route';

const chatRequest = (body: unknown) =>
  new Request('http://localhost/api/chat', { method: 'POST', body: JSON.stringify(body) });

beforeEach(() => {
  vi.clearAllMocks();
  holder.agentCtorArgs.length = 0;
  holder.executeFns.length = 0;
  holder.finalText = 'answer';
  holder.finalFinishReason = 'stop';

  process.env.MEMORY_API_KEY = 'test-key';
  delete process.env.MEMORY_WORKSPACE_ID;
  delete process.env.NAMS_MODE;

  holder.isMcpConfigured.mockReturnValue(false);
  holder.getNamsMcpConfig.mockReturnValue(undefined);
  holder.languageModel.mockReturnValue({ __brand: 'provider-wrapped-model' });
  holder.createNamsProvider.mockReturnValue({ languageModel: holder.languageModel });
  holder.toolsWithMcp.mockResolvedValue({
    tools: { query_memory: {}, store_memory: {} },
    close: vi.fn(),
  });
  holder.wrap.mockImplementation((model: unknown) => ({ __brand: 'middleware-wrapped-model', wraps: model }));
  holder.createNams.mockReturnValue({ toolsWithMcp: holder.toolsWithMcp, wrap: holder.wrap });
  holder.makeClient.mockReturnValue({ reasoning: { recordStep: vi.fn().mockResolvedValue(undefined) } });
  holder.resolveConversation.mockResolvedValue('');

  vi.spyOn(console, 'log').mockImplementation(() => {});
  vi.spyOn(console, 'warn').mockImplementation(() => {});
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

describe('POST /api/chat', () => {
  it('returns 400 for an invalid JSON body', async () => {
    const req = new Request('http://localhost/api/chat', { method: 'POST', body: '{not json' });

    const res = await POST(req);

    expect(res.status).toBe(400);
  });

  it('returns 503 when MEMORY_API_KEY is not set', async () => {
    delete process.env.MEMORY_API_KEY;

    const res = await POST(chatRequest({ messages: [] }));

    expect(res.status).toBe(503);
    expect(holder.createNamsProvider).not.toHaveBeenCalled();
  });

  it('provider mode (default) wraps the model via createNamsProvider and attaches no NAMS tools', async () => {
    const res = await POST(
      chatRequest({ messages: [{ role: 'user', parts: [{ type: 'text', text: 'hi' }] }], userId: 'u1' }),
    );

    expect(res.status).toBe(200);
    expect(holder.createNamsProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        apiKey: 'test-key',
        workspaceId: undefined,
        scope: { userId: 'u1', conversationId: undefined },
      }),
    );
    expect(holder.languageModel).toHaveBeenCalledWith('gpt-5.4-mini');
    expect(holder.createNams).not.toHaveBeenCalled();

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.model).toEqual({ __brand: 'provider-wrapped-model' });
    expect(agentArgs.tools).toBeUndefined();
  });

  it('tools mode leaves the base model unwrapped and sources tools from createNams().toolsWithMcp()', async () => {
    process.env.NAMS_MODE = 'tools';
    holder.getNamsMcpConfig.mockReturnValue({ url: 'https://mcp.example.com/mcp', headers: {} });

    const res = await POST(
      chatRequest({ messages: [{ role: 'user', parts: [{ type: 'text', text: 'hi' }] }], userId: 'u1' }),
    );

    expect(res.status).toBe(200);
    expect(holder.createNamsProvider).not.toHaveBeenCalled();
    expect(holder.createNams).toHaveBeenCalledWith({ apiKey: 'test-key', workspaceId: undefined });
    expect(holder.toolsWithMcp).toHaveBeenCalledWith(
      { userId: 'u1', conversationId: undefined },
      { url: 'https://mcp.example.com/mcp', headers: {} },
    );

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.model).toEqual({ __brand: 'openai-model', modelId: 'gpt-5.4-mini' });
    expect(agentArgs.tools).toEqual({ query_memory: {}, store_memory: {} });
  });

  it('middleware mode wraps the base model via createNams().wrap() and attaches no NAMS tools', async () => {
    process.env.NAMS_MODE = 'middleware';

    const res = await POST(
      chatRequest({ messages: [{ role: 'user', parts: [{ type: 'text', text: 'hi' }] }], userId: 'u1' }),
    );

    expect(res.status).toBe(200);
    expect(holder.createNamsProvider).not.toHaveBeenCalled();
    expect(holder.createNams).toHaveBeenCalledWith({ apiKey: 'test-key', workspaceId: undefined });
    expect(holder.wrap).toHaveBeenCalledWith(
      { __brand: 'openai-model', modelId: 'gpt-5.4-mini' },
      { userId: 'u1', conversationId: undefined },
    );

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.model).toEqual({
      __brand: 'middleware-wrapped-model',
      wraps: { __brand: 'openai-model', modelId: 'gpt-5.4-mini' },
    });
    expect(agentArgs.tools).toBeUndefined();
  });

  it('middleware mode connects MCP tools directly, same as provider mode', async () => {
    process.env.NAMS_MODE = 'middleware';
    holder.isMcpConfigured.mockReturnValue(true);
    holder.getNeo4jMcpTools.mockResolvedValue({ tools: { 'read-cypher': {} }, close: vi.fn() });

    const res = await POST(chatRequest({ messages: [], userId: 'u1' }));

    expect(res.status).toBe(200);
    expect(holder.getNeo4jMcpTools).toHaveBeenCalled();

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.tools).toEqual({ 'read-cypher': {} });
  });

  it('falls back to NAMS-only tools when the MCP connection fails in tools mode', async () => {
    process.env.NAMS_MODE = 'tools';
    holder.toolsWithMcp
      .mockRejectedValueOnce(new Error('mcp down'))
      .mockResolvedValueOnce({ tools: { query_memory: {}, store_memory: {} }, close: vi.fn() });

    const res = await POST(chatRequest({ messages: [], userId: 'u1' }));

    expect(res.status).toBe(200);
    expect(holder.toolsWithMcp).toHaveBeenCalledTimes(2);
    expect(holder.toolsWithMcp).toHaveBeenNthCalledWith(2, { userId: 'u1', conversationId: undefined });
  });

  it('builds the DATABASE ACCESS prompt from the tool names the server actually returned', async () => {
    process.env.NAMS_MODE = 'tools';
    holder.toolsWithMcp.mockResolvedValue({
      tools: { query_memory: {}, store_memory: {}, get_neo4j_schema: {}, read_neo4j_cypher: {} },
      close: vi.fn(),
    });

    await POST(chatRequest({ messages: [], userId: 'u1' }));

    const { instructions } = holder.agentCtorArgs[0];
    expect(instructions).toContain('DATABASE ACCESS');
    expect(instructions).toContain('get_neo4j_schema');
    expect(instructions).toContain('read_neo4j_cypher');
    // memory tools are not database tools
    expect(instructions).not.toMatch(/• query_memory/);
  });

  it('omits the DATABASE ACCESS prompt when MCP is configured but did not connect', async () => {
    process.env.NAMS_MODE = 'tools';
    holder.isMcpConfigured.mockReturnValue(true);
    holder.toolsWithMcp
      .mockRejectedValueOnce(new Error('HTTP 401'))
      .mockResolvedValueOnce({ tools: { query_memory: {}, store_memory: {} }, close: vi.fn() });

    await POST(chatRequest({ messages: [], userId: 'u1' }));

    expect(holder.agentCtorArgs[0].instructions).not.toContain('DATABASE ACCESS');
    expect(holder.explainMcpError).toHaveBeenCalled();
  });

  it('guards the tool loop with enforceQueryMemory in tools mode only', async () => {
    process.env.NAMS_MODE = 'tools';

    await POST(chatRequest({ messages: [], userId: 'u1' }));

    expect(holder.enforceQueryMemory).toHaveBeenCalledWith({ graceSteps: 2 });
    expect(holder.agentCtorArgs[0].prepareStep).toEqual({ __prepareStep: true });

    process.env.NAMS_MODE = 'provider';
    await POST(chatRequest({ messages: [], userId: 'u1' }));

    expect(holder.agentCtorArgs[1].prepareStep).toBeUndefined();
  });

  it('emits fallback text when the tool loop finishes without producing an answer', async () => {
    holder.finalText = '';
    holder.finalFinishReason = 'tool-calls';

    await POST(chatRequest({ messages: [], userId: 'u1' }));

    const writer = { merge: vi.fn(), write: vi.fn() };
    await holder.executeFns[0]({ writer });

    expect(writer.merge).toHaveBeenCalledTimes(1);
    expect(writer.write).toHaveBeenCalledTimes(3);
    expect(writer.write).toHaveBeenNthCalledWith(1, { type: 'text-start', id: 'fallback-text' });
    expect(writer.write).toHaveBeenNthCalledWith(2, expect.objectContaining({
      type: 'text-delta',
      id: 'fallback-text',
      delta: expect.stringContaining('ran out of steps'),
    }));
    expect(writer.write).toHaveBeenNthCalledWith(3, { type: 'text-end', id: 'fallback-text' });
  });

  it('does not emit fallback text when the agent produced an answer', async () => {
    await POST(chatRequest({ messages: [], userId: 'u1' }));

    const writer = { merge: vi.fn(), write: vi.fn() };
    await holder.executeFns[0]({ writer });

    expect(writer.merge).toHaveBeenCalledTimes(1);
    expect(writer.write).not.toHaveBeenCalled();
  });

  it('persists the step trace after the agent finishes via makeClient()/resolveConversation()', async () => {
    holder.resolveConversation.mockResolvedValue('conv-1');

    await POST(chatRequest({ messages: [], userId: 'u1' }));

    const onFinish = holder.agentCtorArgs[0].onFinish;
    await onFinish({
      text: 'answer',
      steps: [{ text: 'looked things up', toolCalls: [{ toolName: 'query_memory' }], toolResults: [] }],
      usage: { inputTokens: 1, outputTokens: 1 },
    });

    expect(holder.makeClient).toHaveBeenCalledWith({ apiKey: 'test-key', workspaceId: undefined });
    expect(holder.resolveConversation).toHaveBeenCalled();
    expect(holder.makeClient.mock.results[0].value.reasoning.recordStep).toHaveBeenCalledWith(
      expect.objectContaining({ conversationId: 'conv-1', actionTaken: 'query_memory' }),
    );
  });
});
