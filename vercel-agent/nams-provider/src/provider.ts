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
  type NamsConfig,
  type NamsScope,
  type GraphExtractor,
  type MemoryHit,
} from './client';
import { createGraphExtractor } from './extract';

export interface NamsMemoryConfig extends NamsConfig {
  /** Max memories injected per turn (default: 6). */
  injectLimit?: number;
  /** Persist each turn to NAMS short-term memory (default: true). */
  persistInteractions?: boolean;
  /** When set, build a real entity graph per stored turn (one extra model call). */
  extractionModel?: LanguageModel;
}

// ─── Prompt helpers

function lastUserText(prompt: any[]): string {
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

function injectIntoLastUser(prompt: any[], block: string): void {
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

function textFromResult(result: any): string {
  if (typeof result?.text === 'string') return result.text;
  if (Array.isArray(result?.content))
    return (result.content as any[])
      .filter(p => p?.type === 'text')
      .map(p => p.text as string)
      .join('');
  return '';
}

function formatMemoryBlock(memories: MemoryHit[]): string {
  return (
    'Relevant long-term memory about this user (use it to personalise your answer):\n' +
    memories.map((m, i) => `${i + 1}. [${m.source}] ${m.content}`).join('\n')
  );
}

// ─── Middleware factory

function buildMiddleware(
  config: NamsMemoryConfig,
  scope: NamsScope,
  extractor: GraphExtractor | undefined,
  injectLimit: number,
  persist: boolean,
): LanguageModelV3Middleware {
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

    // Called by the AI SDK for non-streaming model calls.
    // PURPOSE: after the model responds, persist both the user message and
    // assistant reply to NAMS short-term memory for future retrieval.
    wrapGenerate: async ({ doGenerate, params }) => {
      const result = await doGenerate();
      await persistTurn(params, textFromResult(result))
        .catch(e => console.warn('[nams:provider] persist failed:', e));
      return result;
    },

    wrapStream: async ({ doStream, params }) => {
      const { stream, ...rest } = await doStream();
      let text = '';

      const tap = new TransformStream({
        transform(chunk: any, controller) {
          // V3 uses textDelta; handle both spellings defensively.
          if (chunk?.type === 'text-delta')
            text += (chunk.textDelta ?? chunk.delta ?? chunk.text ?? '') as string;
          else if (chunk?.type === 'text')
            text += (chunk.text ?? '') as string;
          controller.enqueue(chunk);
        },
        async flush() {
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
