/**
 * Mode 1 — Provider (transparent, no tool calls)
 *
 * createNamsMemory(config).wrap(model, scope) returns a LanguageModel that:
 *   • retrieves relevant memories and injects them into the system prompt before every call
 *   • persists the user message + assistant response to NAMS after every call
 *
 * The model never sees query_memory / store_memory — memory is fully automatic.
 *
 * @example
 * const memory = createNamsMemory({ apiKey: process.env.MEMORY_API_KEY! });
 * const model  = memory.wrap(openai('gpt-5.4-mini'), { userId });
 * return streamText({ model, messages }).toUIMessageStreamResponse();
 */

import { wrapLanguageModel, type LanguageModel } from 'ai';
import type { LanguageModelV3, LanguageModelV3Middleware } from '@ai-sdk/provider';
import {
  makeClient,
  resolveConversation,
  retrieveMemories,
} from './client';
import { createGraphExtractor } from './extract';
import { GraphExtractor, MemoryHit, NamsConfig, NamsScope } from './types';

export interface NamsMemoryConfig extends NamsConfig {
  /** Max memories injected per turn (default: 6). */
  injectLimit?: number;
  /** Persist each turn to NAMS short-term memory (default: true). */
  persistInteractions?: boolean;
  /** When set, build a real entity graph per stored turn (one extra model call). */
  extractionModel?: LanguageModel;
}


const injectIntoLastUser = (prompt: any[], block: string): void => {
  for (let i = prompt.length - 1; i >= 0; i--) {
    const msg = prompt[i];
    if (msg?.role !== 'user') continue;
    if (typeof msg.content === 'string') {
      msg.content = `${block}\n\n${msg.content}`;
    } else if (Array.isArray(msg.content)) {
      msg.content.unshift({ type: 'text', text: `${block}\n\n` });
    }
    return;
  }
}

// Step 5: Supporting object generation (generate path) — detects tool-call
// content parts and serializes p.args so structured responses are still
// persisted when there is no result.text (e.g. generateObject in tool mode).
const textFromResult = (result: any): string => {
  if (typeof result?.text === 'string' && result.text) return result.text;
  if (Array.isArray(result?.content)) {
    const textParts = (result.content as any[])
      .filter(p => p?.type === 'text')
      .map(p => p.text as string)
      .join('');
    if (textParts) return textParts;
    return (result.content as any[])
      .filter(p => p?.type === 'tool-call')
      .map(p => { try { return JSON.stringify(p.args); } catch { return ''; } })
      .join('');
  }
  return '';
}

const formatMemoryBlock = (memories: MemoryHit[]): string => {
  return (
    'Relevant long-term memory about this user (use it to personalise your answer):\n' +
    memories.map((m, i) => `${i + 1}. [${m.source}] ${m.content}`).join('\n')
  );
}

// ─── Step 3: Mapping the input — helpers that read and rewrite params.prompt
// before every model call. lastUserText extracts the query; injectIntoLastUser
// prepends the retrieved memory block; textFromResult reads back the response.

const lastUserText = (prompt: any[]): string => {
  for (let i = prompt.length - 1; i >= 0; i--) {
    const msg = prompt[i];
    if (msg?.role !== 'user') continue;
    if (typeof msg.content === 'string') return msg.content;
    if (Array.isArray(msg.content))
      return msg.content
        .filter((p: any) => p?.type === 'text')
        .map((p: any) => p.text as string)
        .join(' ')
        .trim();
  }
  return '';
}

// ─── Step 2: Language model implementation — buildMiddleware returns a
// LanguageModelV3Middleware; wrapLanguageModel (called in createNamsMemory.wrap)
// composes it with any base LanguageModelV3 to produce the final model object.

const buildMiddleware = (
  config: NamsMemoryConfig,
  scope: NamsScope,
  extractor: GraphExtractor | undefined,
  injectLimit: number,
  persist: boolean,
): LanguageModelV3Middleware => {
  const client = makeClient(config);

  // Lazy-resolve the conversation once per wrapped model instance.
  let convIdPromise: Promise<string> | null = null;
  const getConvId = (): Promise<string> =>
    (convIdPromise ??= resolveConversation(client, config, scope));

  // Track the original (pre-injection) user text so we persist the clean version.
  const originalUserText = new WeakMap<object, string>();

  async function persistTurn(params: any, assistantText: string): Promise<void> {
    if (!persist) return;
    const convId = await getConvId();
    const userText = originalUserText.get(params as object) ?? lastUserText(params.prompt);
    if (userText) await client.shortTerm.addMessage(convId, 'user', userText).catch(() => { });
    if (assistantText) await client.shortTerm.addMessage(convId, 'assistant', assistantText).catch(() => { });
    if (extractor && (userText || assistantText)) {
      const combined = `User: ${userText}\nAssistant: ${assistantText}`.trim();
      await extractor(client, { content: combined, type: 'interaction' })
        .catch(e => console.warn('[nams] turn extraction failed:', e));
    }
  }

  return {
    specificationVersion: 'v3',
    // Step 3: Mapping the input — fetch memories for the user query and inject
    // them into params.prompt before the model ever sees the request.
    transformParams: async ({ params }) => {
      const userText = lastUserText(params.prompt);
      if (!userText) return params;

      originalUserText.set(params as object, userText);

      const convId = await getConvId();
      const memories = await retrieveMemories(client, scope, convId, userText, injectLimit)
        .catch(e => { console.warn('[nams:provider] retrieve failed:', e); return [] as MemoryHit[]; });

      if (memories.length === 0) {
        console.log(`[nams:provider] No memories found — prompt unchanged`);
        return params;
      }

      injectIntoLastUser(params.prompt, formatMemoryBlock(memories));
      return params;
    },

    // Step 4: Processing the results (generate) — doGenerate() runs the model;
    // textFromResult extracts the assistant text; persistTurn saves the turn.
    wrapGenerate: async ({ doGenerate, params }) => {
      const result = await doGenerate();
      await persistTurn(params, textFromResult(result))
        .catch(e => console.warn('[nams:provider] persist failed:', e));
      return result;
    },

    // Step 4: Processing the results (streaming + tool calls) — tap the live
    // stream to accumulate text-delta, tool-call-delta (streamed args), and
    // tool-call chunks; persist the full turn in flush once the stream closes.
    //
    // Step 5: Supporting object generation — tool-call-delta chunks carry the
    // streamed JSON args for generateObject(); pendingToolArgs reassembles them
    // and the non-streaming tool-call branch handles the synchronous case.
    wrapStream: async ({ doStream, params }) => {
      const { stream, ...rest } = await doStream();
      let text = '';
      const pendingToolArgs = new Map<string, string>();

      const tap = new TransformStream({
        transform(chunk: any, controller) {
          // V3 uses textDelta; handle both spellings defensively.
          if (chunk?.type === 'text-delta')
            text += (chunk.textDelta ?? chunk.delta ?? chunk.text ?? '') as string;
          else if (chunk?.type === 'text')
            text += (chunk.text ?? '') as string;
          else if (chunk?.type === 'tool-call-delta') {
            const id = chunk.toolCallId as string;
            pendingToolArgs.set(id, (pendingToolArgs.get(id) ?? '') + (chunk.argsTextDelta ?? ''));
          } else if (chunk?.type === 'tool-call') {
            // Step 5: non-streaming object generation — serialize structured args.
            try { text += JSON.stringify(chunk.args); } catch { /* skip */ }
          }
          controller.enqueue(chunk);
        },
        async flush() {
          for (const args of pendingToolArgs.values()) {
            if (args) text += args;
          }
          await persistTurn(params, text)
            .catch(e => console.warn('[nams:provider] persist failed:', e));
        },
      });

      return { stream: stream.pipeThrough(tap), ...rest };
    },
  };
}

/**
 * Create a NAMS memory provider to getmemory
 */
// Step 2: Language model implementation — wrap() calls wrapLanguageModel to
// compose the middleware with any base LanguageModelV3, returning a drop-in
// LanguageModelV3 with transparent NAMS memory.
export function createNamsMemory(config: NamsMemoryConfig) {
  const extractor = config.extractionModel ? createGraphExtractor(config.extractionModel) : undefined;
  const injectLimit = config.injectLimit ?? 6;
  const persist = config.persistInteractions ?? true;

  return {
    wrap(model: LanguageModelV3, scope: NamsScope, providerId?: string): LanguageModelV3 {
      const middleware = buildMiddleware(config, scope, extractor, injectLimit, persist);
      return wrapLanguageModel({ model, middleware, ...(providerId && { providerId }) });
    },
  };
}
