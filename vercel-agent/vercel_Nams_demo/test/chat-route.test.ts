/** POST /api/chat — checks how each NAMS_MODE wires memory into the agent, plus error paths. */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const holder = vi.hoisted(() => ({
  agentCtorArgs: [] as any[],
  agents: [] as any[],
  executeFns: [] as any[],
  finalText: 'answer',
  finalFinishReason: 'stop',
  createNamsProvider: vi.fn(),
  createNams: vi.fn(),
  languageModel: vi.fn(),
  wrap: vi.fn(),
  toolsWithMcp: vi.fn(),
  hooks: vi.fn(),
  loadSession: vi.fn(),
  sessionOnFinish: vi.fn(),
  sessionSave: vi.fn(),
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
    holder.agents.push(this);
    this.stream = vi.fn().mockResolvedValue({
      stream: new ReadableStream(),
      text: Promise.resolve(holder.finalText),
      finishReason: Promise.resolve(holder.finalFinishReason),
      toUIMessageStream: vi.fn(() => new ReadableStream()),
    });
  }),
  createUIMessageStream: vi.fn(({ execute }: any) => {
    holder.executeFns.push(execute);
    return { __execute: execute };
  }),
  createUIMessageStreamResponse: vi.fn(() => new Response(null, { status: 200 })),
  stepCountIs: vi.fn((n: number) => ({ __stepCountIs: n })),
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
  guardTools: vi.fn((tools: unknown) => tools),
}));

import { POST } from '../app/api/chat/route';

const chatRequest = (body: unknown) =>
  new Request('http://localhost/api/chat', { method: 'POST', body: JSON.stringify(body) });

const userMessage = (text: string) => ({ role: 'user', parts: [{ type: 'text', text }] });

beforeEach(() => {
  vi.clearAllMocks();
  holder.agentCtorArgs.length = 0;
  holder.agents.length = 0;
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
    close: vi.fn().mockResolvedValue(undefined),
  });
  holder.wrap.mockImplementation((model: unknown) => ({ __brand: 'middleware-wrapped-model', wraps: model }));
  holder.loadSession.mockResolvedValue([]);
  holder.sessionSave.mockResolvedValue(undefined);
  holder.sessionOnFinish.mockReturnValue(holder.sessionSave);
  holder.hooks.mockReturnValue({ loadSession: holder.loadSession, onFinish: holder.sessionOnFinish });
  holder.createNams.mockReturnValue({ toolsWithMcp: holder.toolsWithMcp, wrap: holder.wrap, hooks: holder.hooks });
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

  it('returns 400 when the request has no user message', async () => {
    const res = await POST(chatRequest({ message: { role: 'assistant', parts: [] }, userId: 'u1' }));

    expect(res.status).toBe(400);
    expect(holder.agentCtorArgs).toHaveLength(0);
  });

  it('returns 503 when MEMORY_API_KEY is not set', async () => {
    delete process.env.MEMORY_API_KEY;

    const res = await POST(chatRequest({ message: userMessage('hi') }));

    expect(res.status).toBe(503);
    expect(holder.createNamsProvider).not.toHaveBeenCalled();
  });

  it('provider mode (default) wraps the model via createNamsProvider and attaches no NAMS tools', async () => {
    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(res.status).toBe(200);
    expect(holder.createNamsProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        apiKey: 'test-key',
        workspaceId: undefined,
        scope: { userId: 'u1', conversationId: undefined },
      }),
    );
    expect(holder.languageModel).toHaveBeenCalledWith('gpt-5.4-mini');
    expect(holder.wrap).not.toHaveBeenCalled();

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.model).toEqual({ __brand: 'provider-wrapped-model' });
    expect(agentArgs.tools).toBeUndefined();
  });

  it('tools mode leaves the base model unwrapped and sources tools from createNams().toolsWithMcp()', async () => {
    process.env.NAMS_MODE = 'tools';
    holder.getNamsMcpConfig.mockReturnValue({ url: 'https://mcp.example.com/mcp', headers: {} });

    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

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

    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

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

    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(res.status).toBe(200);
    expect(holder.getNeo4jMcpTools).toHaveBeenCalled();

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.tools).toEqual({ 'read-cypher': {} });
  });

  it('hooks mode leaves the model unwrapped and attaches no NAMS tools', async () => {
    process.env.NAMS_MODE = 'hooks';

    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(res.status).toBe(200);
    expect(holder.createNamsProvider).not.toHaveBeenCalled();
    expect(holder.wrap).not.toHaveBeenCalled();
    expect(holder.toolsWithMcp).not.toHaveBeenCalled();

    const agentArgs = holder.agentCtorArgs[0];
    expect(agentArgs.model).toEqual({ __brand: 'openai-model', modelId: 'gpt-5.4-mini' });
    expect(agentArgs.tools).toBeUndefined();
    expect(agentArgs.prepareStep).toBeUndefined();
    expect(agentArgs.instructions).toContain('restored from NAMS');
  });

  it.each(['provider', 'middleware', 'tools', 'hooks'])(
    '%s mode streams the history restored from NAMS plus the new message',
    async (mode) => {
      process.env.NAMS_MODE = mode;
      holder.loadSession.mockResolvedValue([
        { role: 'user', content: 'my name is Alex' },
        { role: 'assistant', content: 'Hi Alex!' },
      ]);

      await POST(chatRequest({ message: userMessage('what is my name?'), userId: 'u1' }));

      expect(holder.hooks).toHaveBeenCalledWith({ userId: 'u1', conversationId: undefined });
      await holder.executeFns[0]({ writer: { merge: vi.fn(), write: vi.fn() } });
      expect(holder.agents[0].stream).toHaveBeenCalledWith({
        messages: [
          { role: 'user', content: 'my name is Alex' },
          { role: 'assistant', content: 'Hi Alex!' },
          { role: 'user', content: 'what is my name?' },
        ],
      });
    },
  );

  it('drops the saved question and old answer when the message is re-run', async () => {
    holder.loadSession.mockResolvedValue([
      { role: 'user', content: 'my name is Alex' },
      { role: 'assistant', content: 'Hi Alex!' },
      { role: 'user', content: 'what is my name?' },
      { role: 'assistant', content: 'a bad answer' },
    ]);

    await POST(chatRequest({ message: userMessage('what is my name?'), trigger: 'regenerate-message', userId: 'u1' }));

    await holder.executeFns[0]({ writer: { merge: vi.fn(), write: vi.fn() } });
    expect(holder.agents[0].stream).toHaveBeenCalledWith({
      messages: [
        { role: 'user', content: 'my name is Alex' },
        { role: 'assistant', content: 'Hi Alex!' },
        { role: 'user', content: 'what is my name?' },
      ],
    });
  });

  it('hooks mode saves the turn through the session before recording the trace', async () => {
    process.env.NAMS_MODE = 'hooks';
    holder.resolveConversation.mockResolvedValue('conv-1');
    const order: string[] = [];
    holder.sessionSave.mockImplementation(async () => { order.push('save'); });
    holder.resolveConversation.mockImplementation(async () => { order.push('trace'); return 'conv-1'; });

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    const responseMessages = [{ role: 'assistant', content: [{ type: 'text', text: 'hello' }] }];
    await holder.agentCtorArgs[0].onFinish({
      text: 'hello',
      steps: [{ text: 'hello', toolCalls: [], toolResults: [] }],
      usage: undefined,
      responseMessages,
    });

    expect(holder.sessionOnFinish).toHaveBeenCalledWith({ prompt: 'hi' });
    expect(holder.sessionSave).toHaveBeenCalledWith({ text: 'hello', responseMessages });
    expect(order).toEqual(['save', 'trace']);
  });

  it('tools mode saves the text of the turn, without its tool calls', async () => {
    process.env.NAMS_MODE = 'tools';

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));
    await holder.agentCtorArgs[0].onFinish({
      text: 'hello',
      steps: [],
      usage: undefined,
      responseMessages: [{ role: 'tool', content: [{ type: 'tool-result', toolName: 'query_memory' }] }],
    });

    expect(holder.sessionOnFinish).toHaveBeenCalledWith({ prompt: 'hi' });
    expect(holder.sessionSave).toHaveBeenCalledWith({ text: 'hello' });
  });

  it('hooks mode connects MCP tools directly, same as provider mode', async () => {
    process.env.NAMS_MODE = 'hooks';
    holder.isMcpConfigured.mockReturnValue(true);
    holder.getNeo4jMcpTools.mockResolvedValue({ tools: { 'read-cypher': {} }, close: vi.fn() });

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(holder.getNeo4jMcpTools).toHaveBeenCalled();
    expect(holder.agentCtorArgs[0].tools).toEqual({ 'read-cypher': {} });
  });

  it('returns 503 for an unknown NAMS_MODE instead of running without memory', async () => {
    process.env.NAMS_MODE = 'session';

    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: expect.stringContaining('Unknown NAMS_MODE "session"') });
    expect(holder.agentCtorArgs).toHaveLength(0);
  });

  it('falls back to NAMS-only tools when the MCP connection fails in tools mode', async () => {
    process.env.NAMS_MODE = 'tools';
    holder.toolsWithMcp
      .mockRejectedValueOnce(new Error('mcp down'))
      .mockResolvedValueOnce({ tools: { query_memory: {}, store_memory: {} }, close: vi.fn() });

    const res = await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

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

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

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

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(holder.agentCtorArgs[0].instructions).not.toContain('DATABASE ACCESS');
    expect(holder.explainMcpError).toHaveBeenCalled();
  });

  it('guards the tool loop with enforceQueryMemory in tools mode only', async () => {
    process.env.NAMS_MODE = 'tools';

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(holder.enforceQueryMemory).toHaveBeenCalledWith({ graceSteps: 2 });
    expect(holder.agentCtorArgs[0].prepareStep).toEqual({ __prepareStep: true });

    process.env.NAMS_MODE = 'provider';
    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    expect(holder.agentCtorArgs[1].prepareStep).toBeUndefined();
  });

  it('emits fallback text when the tool loop finishes without producing an answer', async () => {
    holder.finalText = '';
    holder.finalFinishReason = 'tool-calls';

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

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
    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

    const writer = { merge: vi.fn(), write: vi.fn() };
    await holder.executeFns[0]({ writer });

    expect(writer.merge).toHaveBeenCalledTimes(1);
    expect(writer.write).not.toHaveBeenCalled();
  });

  it('persists the step trace after the agent finishes via makeClient()/resolveConversation()', async () => {
    holder.resolveConversation.mockResolvedValue('conv-1');

    await POST(chatRequest({ message: userMessage('hi'), userId: 'u1' }));

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
