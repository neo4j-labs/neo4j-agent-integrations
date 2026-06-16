/**
 * nams-provider.ts — First-class Vercel AI SDK provider for Neo4j NAMS memory.
 *
 * Uses wrapLanguageModel (LanguageModelV3Middleware) so NAMS tool calls run
 * inside the model layer, completely transparent to streamText callers.
 *
 * Two helpers are exported:
 *   wrapModel(model)    — wrap a single LanguageModelV3
 *   wrapProvider(prov)  — wrap an entire provider (e.g. openai) so every
 *                         model it returns has NAMS memory baked in
 *
 * Usage (provider approach):
 *   import { createNamsProvider } from '@/lib/nams-provider';
 *   const nams = createNamsProvider({ apiKey, userId });
 *
 *   // Every model call auto-queries and stores memory — no tools: needed
 *   streamText({ model: nams.wrapModel(openai('gpt-4o-mini')), system, messages });
 *
 *   // Or wrap the whole provider
 *   const memOpenAI = nams.wrapProvider(openai);
 *   streamText({ model: memOpenAI('gpt-4o-mini'), system, messages });
 */

import type {
  LanguageModelV3,
  LanguageModelV3CallOptions,
  LanguageModelV3FunctionTool,
  LanguageModelV3Middleware,
  LanguageModelV3StreamPart,
  LanguageModelV3StreamResult,
  LanguageModelV3TextPart,
  LanguageModelV3ToolCall,
  LanguageModelV3ToolCallPart,
  ProviderV3,
} from '@ai-sdk/provider';
import { wrapLanguageModel, wrapProvider as sdkWrapProvider } from 'ai';
import {
  getOrCreateConversation,
  executeQueryMemory,
  executeStoreMemory,
  type NamsMemoryOptions,
  type QueryInput,
  type StoreInput,
} from './nams-memory-provider';

// ─── Narrowed assistant-message content type ──────────────────────────────────
// The 'assistant' role in LanguageModelV3Message only accepts these part types.
type AssistantPart = Parameters<
  Extract<LanguageModelV3CallOptions['prompt'][number], { role: 'assistant' }>['content']['push']
>[0];

// ─── Tool definitions (JSON Schema for the model to see) ─────────────────────

const QUERY_MEMORY_TOOL: LanguageModelV3FunctionTool = {
  type: 'function',
  name: 'query_memory',
  description:
    'Search NAMS (Neo4j Agent Memory System) for context relevant to the current message. ' +
    'Call this FIRST every turn before answering.',
  inputSchema: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'Keywords or phrase to search in memory' },
      limit: { type: 'integer', minimum: 1, maximum: 20, default: 5 },
    },
    required: ['query'],
    additionalProperties: false,
  },
};

const STORE_MEMORY_TOOL: LanguageModelV3FunctionTool = {
  type: 'function',
  name: 'store_memory',
  description:
    'Persist important information to NAMS (Neo4j graph). ' +
    'Call this AFTER your response to save facts, preferences, and patterns.',
  inputSchema: {
    type: 'object',
    properties: {
      content: { type: 'string', minLength: 1, maxLength: 2000, description: 'The information to remember' },
      type: {
        type: 'string',
        enum: ['fact', 'interaction', 'pattern', 'user_preference'],
        description:
          'fact=persistent knowledge | interaction=conversation event | ' +
          'pattern=recurring behaviour | user_preference=explicit setting',
      },
      confidence: { type: 'number', minimum: 0, maximum: 1, description: 'Confidence 0–1' },
      tags: { type: 'array', items: { type: 'string', maxLength: 40 }, maxItems: 10, default: [] },
    },
    required: ['content', 'type', 'confidence'],
    additionalProperties: false,
  },
};

const NAMS_TOOL_NAMES = new Set(['query_memory', 'store_memory']);

// ─── Internal helpers ─────────────────────────────────────────────────────────

async function dispatchNamsTool(
  toolName: string,
  rawInput: string,
  opts: NamsMemoryOptions,
): Promise<unknown> {
  const { client, convId } = await getOrCreateConversation(opts);
  const input = JSON.parse(rawInput);
  if (toolName === 'query_memory') return executeQueryMemory(client, opts.userId, convId, input as QueryInput);
  if (toolName === 'store_memory') return executeStoreMemory(client, opts.userId, convId, input as StoreInput);
  throw new Error(`[nams-provider] Unknown NAMS tool: ${toolName}`);
}

function replayStream(chunks: LanguageModelV3StreamPart[]): ReadableStream<LanguageModelV3StreamPart> {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    },
  });
}

/** Convert stream chunks into the narrowed AssistantPart[] needed for prompt messages. */
function chunksToAssistantParts(chunks: LanguageModelV3StreamPart[]): AssistantPart[] {
  let textBuffer = '';
  const toolCallParts: LanguageModelV3ToolCallPart[] = [];

  for (const chunk of chunks) {
    if (chunk.type === 'text-delta') {
      textBuffer += (chunk as unknown as { text: string }).text;
    } else if (chunk.type === 'tool-call') {
      const tc = chunk as unknown as LanguageModelV3ToolCall;
      toolCallParts.push({
        type: 'tool-call',
        toolCallId: tc.toolCallId,
        toolName: tc.toolName,
        input: JSON.parse(tc.input),
      });
    }
  }

  const textPart: LanguageModelV3TextPart[] = textBuffer
    ? [{ type: 'text', text: textBuffer }]
    : [];

  return [...textPart, ...toolCallParts] as AssistantPart[];
}

/** Convert generate-result content into the narrowed AssistantPart[] for prompt messages. */
function contentToAssistantParts(
  content: Awaited<ReturnType<LanguageModelV3['doGenerate']>>['content'],
): AssistantPart[] {
  return content
    .filter(c => c.type === 'text' || c.type === 'reasoning' || c.type === 'file' || c.type === 'tool-call')
    .map(c => {
      if (c.type === 'tool-call') {
        const tc = c as LanguageModelV3ToolCall;
        return {
          type: 'tool-call' as const,
          toolCallId: tc.toolCallId,
          toolName: tc.toolName,
          input: JSON.parse(tc.input),
        } satisfies LanguageModelV3ToolCallPart;
      }
      return c as unknown as AssistantPart;
    });
}

// ─── Middleware factory ───────────────────────────────────────────────────────

export interface NamsProviderOptions extends NamsMemoryOptions {
  /** Maximum internal NAMS tool-call rounds per model call (default: 5). */
  maxMemorySteps?: number;
}

function createNamsMiddleware(opts: NamsProviderOptions): LanguageModelV3Middleware {
  const maxSteps = opts.maxMemorySteps ?? 5;

  return {
    specificationVersion: 'v3',

    overrideProvider: () => 'nams',

    /** Inject NAMS tool definitions before every model call. */
    transformParams: async ({ params }) => ({
      ...params,
      tools: [QUERY_MEMORY_TOOL, STORE_MEMORY_TOOL, ...(params.tools ?? [])],
    }),

    /**
     * Non-streaming: run an internal loop so NAMS tool calls never surface
     * to the streamText caller.  Each round executes the NAMS tools and
     * feeds the results back until the model produces a text-only response.
     */
    wrapGenerate: async ({ doGenerate, params, model }) => {
      let result = await doGenerate();
      let currentParams: LanguageModelV3CallOptions = params;

      for (let step = 0; step < maxSteps; step++) {
        const namsCalls = result.content.filter(
          (c): c is LanguageModelV3ToolCall =>
            c.type === 'tool-call' && NAMS_TOOL_NAMES.has((c as LanguageModelV3ToolCall).toolName),
        );
        if (namsCalls.length === 0) break;

        const toolResults = await Promise.all(
          namsCalls.map(async (call) => {
            const output = await dispatchNamsTool(call.toolName, call.input, opts);
            return {
              type: 'tool-result' as const,
              toolCallId: call.toolCallId,
              toolName: call.toolName,
              output: { type: 'text' as const, value: JSON.stringify(output) },
            };
          }),
        );

        currentParams = {
          ...currentParams,
          prompt: [
            ...currentParams.prompt,
            { role: 'assistant' as const, content: contentToAssistantParts(result.content) },
            { role: 'tool' as const, content: toolResults },
          ],
        };

        result = await model.doGenerate(currentParams);
      }

      return result;
    },

    /**
     * Streaming: consume each NAMS-tool round to collect tool calls, execute
     * them, then stream the final text response normally.
     */
    wrapStream: async ({ doStream, params, model }) => {
      let currentParams: LanguageModelV3CallOptions = params;

      // Normalise doStream (PromiseLike) and subsequent model.doStream (PromiseLike)
      // into plain async functions so TypeScript is happy.
      let getStream: () => Promise<LanguageModelV3StreamResult> =
        () => Promise.resolve(doStream());

      for (let step = 0; step < maxSteps; step++) {
        const { stream, ...streamMeta } = await getStream();

        const chunks: LanguageModelV3StreamPart[] = [];
        const reader = stream.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
        }

        const namsCalls = chunks.filter(
          (c): c is LanguageModelV3ToolCall & LanguageModelV3StreamPart =>
            c.type === 'tool-call' &&
            NAMS_TOOL_NAMES.has((c as unknown as LanguageModelV3ToolCall).toolName),
        );

        if (namsCalls.length === 0) {
          return { stream: replayStream(chunks), ...streamMeta };
        }

        const toolResults = await Promise.all(
          namsCalls.map(async (call) => {
            const tc = call as unknown as LanguageModelV3ToolCall;
            const output = await dispatchNamsTool(tc.toolName, tc.input, opts);
            return {
              type: 'tool-result' as const,
              toolCallId: tc.toolCallId,
              toolName: tc.toolName,
              output: { type: 'text' as const, value: JSON.stringify(output) },
            };
          }),
        );

        const assistantParts = chunksToAssistantParts(chunks);

        currentParams = {
          ...currentParams,
          prompt: [
            ...currentParams.prompt,
            {
              role: 'assistant' as const,
              content: assistantParts.length > 0
                ? assistantParts
                : [{ type: 'text' as const, text: '' }] as AssistantPart[],
            },
            { role: 'tool' as const, content: toolResults },
          ],
        };

        getStream = () => Promise.resolve(model.doStream(currentParams));
      }

      return Promise.resolve(model.doStream(currentParams));
    },
  };
}

// ─── Public API ───────────────────────────────────────────────────────────────

/**
 * Returns helpers to wrap a model or an entire provider with transparent
 * NAMS memory (query + store happen inside the model layer).
 *
 * @example
 * const nams = createNamsProvider({ apiKey, userId });
 *
 * // Wrap a single model
 * streamText({ model: nams.wrapModel(openai('gpt-4o-mini')), system, messages });
 *
 * // Wrap a whole provider (every model inherits NAMS memory)
 * const memOpenAI = nams.wrapProvider(openai);
 * streamText({ model: memOpenAI('gpt-4o-mini'), system, messages });
 */
export function createNamsProvider(opts: NamsProviderOptions) {
  const middleware = createNamsMiddleware(opts);

  return {
    /** Wrap a single LanguageModelV3 with NAMS memory middleware. */
    wrapModel(model: LanguageModelV3): LanguageModelV3 {
      return wrapLanguageModel({ model, middleware });
    },

    /** Wrap an entire ProviderV3 so every language model it returns has NAMS memory. */
    wrapProvider(provider: ProviderV3): ProviderV3 {
      return sdkWrapProvider({ provider, languageModelMiddleware: middleware });
    },
  };
}
