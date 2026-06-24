/**
 * ProviderV3-compatible NAMS provider for the Vercel AI SDK community listing.
 *
 * Wraps any base AI SDK provider (openai, anthropic, etc.) with NAMS long-term
 * memory — retrieved automatically on every call, persisted after every response.
 *
 * @example
 * ```ts
 * import { createNamsProvider } from '@your-org/nams-ai-provider';
 * import { openai } from '@ai-sdk/openai';
 *
 * const nams = createNamsProvider({
 *   apiKey: process.env.MEMORY_API_KEY!,
 *   baseProvider: openai,
 *   scope: { userId: session.userId },
 * });
 *
 * // Drop-in replacement for any model — memory is fully automatic.
 * const { textStream } = streamText({
 *   model: nams.languageModel('gpt-4o-mini'),
 *   messages,
 * });
 * ```
 */

import type { ProviderV3, LanguageModelV3, EmbeddingModelV3, ImageModelV3 } from '@ai-sdk/provider';
import { NoSuchModelError } from '@ai-sdk/provider';
import type { LanguageModel } from 'ai';
import type { NamsConfig, NamsScope } from './client';
import { createNamsMemory } from './provider';

export interface NamsProviderOptions extends NamsConfig {
  /**
   * The base AI SDK provider factory to delegate model resolution to.
   * Pass the provider function directly, e.g. `openai` from `@ai-sdk/openai`.
   */
  baseProvider: (modelId: string) => LanguageModelV3;
  /**
   * User/conversation scope for this provider instance.
   * Create one provider instance per user session.
   */
  scope: NamsScope;
  /** Max memories injected per turn (default: 6). */
  injectLimit?: number;
  /** Persist each turn to NAMS short-term memory (default: true). */
  persistInteractions?: boolean;
  /** When set, builds a real entity graph per stored turn (one extra model call). */
  extractionModel?: LanguageModel;
}

/**
 * Returns a ProviderV3-compatible NAMS provider that can be registered with the
 * Vercel AI SDK via `experimental_createProviderRegistry`.
 *
 * Every `languageModel(modelId)` call resolves the model through `baseProvider`,
 * then wraps it with the NAMS memory middleware transparently.
 */
export function createNamsProvider(options: NamsProviderOptions): ProviderV3 {
  const { baseProvider, scope, ...memoryConfig } = options;
  const memory = createNamsMemory(memoryConfig);

  return {
    specificationVersion: 'v3',

    languageModel(modelId: string): LanguageModelV3 {
      const base = baseProvider(modelId);
      return memory.wrap(base, scope, 'nams');
    },

    embeddingModel(modelId: string): EmbeddingModelV3 {
      throw new NoSuchModelError({ modelId, modelType: 'embeddingModel' });
    },

    imageModel(modelId: string): ImageModelV3 {
      throw new NoSuchModelError({ modelId, modelType: 'imageModel' });
    },
  };
}
