/**
 * providers.mjs — LLM Provider Configuration
 *
 * The Vercel AI SDK supports multiple LLM providers through a unified interface.
 * Select the active provider via the AI_PROVIDER environment variable:
 *
 *   AI_PROVIDER=openai    (default)  → OPENAI_API_KEY required
 *   AI_PROVIDER=google               → GOOGLE_GENERATIVE_AI_API_KEY required
 *                                      npm install @ai-sdk/google
 *   AI_PROVIDER=anthropic            → ANTHROPIC_API_KEY required
 *                                      npm install @ai-sdk/anthropic
 *
 * Optionally set AI_MODEL to override the provider default:
 *   AI_MODEL=gpt-5.4-mini
 */

const PROVIDER_DEFAULTS = {
  openai:    'gpt-5.4-mini',
  google:    'gemini-2.0-flash',
  anthropic: 'claude-3-5-sonnet-20241022',
  mistral:   'mistral-large-latest',
};

/**
 * Returns the provider factory itself plus the resolved model id.
 * Needed by NAMS provider mode, which wraps a provider rather than a model
 * instance (`createNamsProvider({ baseProvider, ... })`).
 *
 * Loads the provider package lazily so unused providers don't need to be installed.
 *
 * @returns {Promise<{ provider: (modelId: string) => any, modelName: string, providerName: string }>}
 */
export async function getProvider() {
  const providerName = process.env.AI_PROVIDER || 'openai';
  const modelName    = process.env.AI_MODEL     || PROVIDER_DEFAULTS[providerName];

  if (!modelName) {
    throw new Error(
      `No default model for provider "${providerName}". Set AI_MODEL in your environment.`
    );
  }

  let provider;
  try {
    switch (providerName) {
      case 'openai': {
        const { openai } = await import('@ai-sdk/openai');
        provider = openai;
        break;
      }
      case 'google': {
        const { google } = await import('@ai-sdk/google');
        provider = google;
        break;
      }
      case 'anthropic': {
        const { anthropic } = await import('@ai-sdk/anthropic');
        provider = anthropic;
        break;
      }
      case 'mistral': {
        const { mistral } = await import('@ai-sdk/mistral');
        provider = mistral;
        break;
      }
      default:
        throw new Error(
          `Unknown AI provider "${providerName}". Supported: openai, google, anthropic, mistral`
        );
    }
  } catch (err) {
    if (err.code === 'ERR_MODULE_NOT_FOUND' || err.code === 'MODULE_NOT_FOUND') {
      throw new Error(
        `Provider package "@ai-sdk/${providerName}" is not installed.\n` +
        `Run: npm install @ai-sdk/${providerName}`
      );
    }
    throw err;
  }

  console.log(`LLM: ${providerName} / ${modelName}`);
  return { provider, modelName, providerName };
}

/**
 * Returns a model instance for the currently configured provider.
 *
 * @returns {Promise<import('ai').LanguageModel>}
 */
export async function getModel() {
  const { provider, modelName } = await getProvider();
  return provider(modelName);
}
