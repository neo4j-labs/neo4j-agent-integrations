# @neo4j-labs/nams-ai-provider

Community provider for the [Vercel AI SDK](https://sdk.vercel.ai) that adds persistent cross-session memory to any language model, backed by the [Neo4j Agent Memory Service (NAMS)](https://memory.neo4jlabs.com).

On every turn, NAMS automatically retrieves relevant memories from the user's history and injects them into the prompt — then persists the response so future sessions remember it. No Neo4j infrastructure to manage.

## What does it do?

Without this package, every chat session starts fresh — the model has no recollection of who the user is, what they've said before, or what decisions were made in prior conversations.

`@neo4j-labs/nams-ai-provider` wraps your existing AI model and transparently adds memory to every call:

1. **Before the model responds** — NAMS searches its memory store for facts, preferences, and past interactions relevant to the current message, then injects them into the prompt automatically.
2. **After the model responds** — NAMS persists the exchange (and optionally extracts entities into a Neo4j knowledge graph) so the next session can recall it.

The result: your AI remembers users across sessions without you changing your application logic.

```
User message
     │
     ▼
┌─────────────────────────────┐
│  NAMS: fetch relevant       │  ← searches long-term graph,
│  memories from Neo4j        │    past sessions, reasoning traces
└────────────┬────────────────┘
             │  memories injected into prompt
             ▼
┌─────────────────────────────┐
│  Your LLM (GPT, Claude…)    │  ← responds with full context
└────────────┬────────────────┘
             │  response
             ▼
┌─────────────────────────────┐
│  NAMS: persist & extract    │  ← stores turn, builds knowledge graph
└─────────────────────────────┘
```

## Setup

**1. Install**

> **Note:** This package is not yet published to npm. Use one of the options below.


**Publish to npm** (requires `@neo4j-labs` org access)

```bash
cd vercel-agent/nams-provider
npm run build
npm publish --access public #requires you to be logged in to https://registry.npmjs.org/
```

Then install normally into your desired project:

```bash
npm install @neo4j-labs/nams-ai-provider or npm install --legacy-peer-deps
```

**2. Install peer dependencies** (if not already present)

```bash
npm install ai @ai-sdk/provider @neo4j-labs/agent-memory zod or npm install --legacy-peer-deps
```

**3. Get a free API key** at [memory.neo4jlabs.com](https://memory.neo4jlabs.com)

```env
MEMORY_API_KEY=sk-nams-...
```

---

## Quick Start

Once installed and your API key is set, adding memory to your Vercel AI SDK app is a one-line model swap:

```ts
// Before: plain agent, no memory
import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
} from 'ai';

const agent = new ToolLoopAgent({
  model:        openai('gpt-4o-mini'),
  instructions: 'You are a helpful assistant.',
  stopWhen:     stepCountIs(10),
});

const stream = createUIMessageStream({
  execute: async ({ writer }) => {
    const result = await agent.stream({ messages });
    writer.merge(result.toUIMessageStream());
  },
});

return createUIMessageStreamResponse({ stream });
```

```ts
// After: swap model → agent now remembers users across sessions
import { createNamsProvider } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
} from 'ai';

const nams = createNamsProvider({
  apiKey:       process.env.MEMORY_API_KEY!,
  baseProvider: openai,
  scope:        { userId: 'user-123' },  // identify the user
});

const agent = new ToolLoopAgent({
  model:        nams.languageModel('gpt-4o-mini'),  // ← only change
  instructions: 'You are a helpful assistant.',
  stopWhen:     stepCountIs(10),
});

const stream = createUIMessageStream({
  execute: async ({ writer }) => {
    const result = await agent.stream({ messages });
    writer.merge(result.toUIMessageStream());
  },
});

return createUIMessageStreamResponse({ stream });
```

**What happens automatically on every call:**
- Relevant memories for `user-123` are fetched and prepended to the prompt
- The model's response is saved back to memory for future sessions
- No other code changes needed

---

## Usage Modes

There are three ways to integrate NAMS depending on how much control you want:

| Mode | How it works | Best for |
|------|-------------|----------|
| **Provider** | Swap your model for a NAMS-wrapped one | Simplest integration, fully transparent |
| **Middleware** | Wrap an existing model instance | When you already have a model configured |
| **Tools** | Expose memory as explicit AI SDK tools | When you want the model to decide when to remember |

---

## Provider Mode (ProviderV3)

Drop NAMS into any Vercel AI SDK project as a standard `ProviderV3`. Memory is fully transparent — no tools, no system prompt changes needed.

```ts
import { createNamsProvider } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
} from 'ai';

// One instance per user session
const nams = createNamsProvider({
  apiKey:       process.env.MEMORY_API_KEY!,
  baseProvider: openai,               // any @ai-sdk/* provider
  scope:        { userId: session.userId },
});

const agent = new ToolLoopAgent({
  model:        nams.languageModel('gpt-5.4-mini'),
  instructions: 'You are a helpful assistant.',
  stopWhen:     stepCountIs(1),       // no tools needed in provider mode
});

const stream = createUIMessageStream({
  execute: async ({ writer }) => {
    const result = await agent.stream({ messages });
    writer.merge(result.toUIMessageStream());
  },
});

return createUIMessageStreamResponse({ stream });
```

Works with the provider registry:

```ts
import { createProviderRegistry as createRegistry } from 'ai';

const registry = createRegistry({
  nams: createNamsProvider({
    apiKey:       process.env.MEMORY_API_KEY!,
    baseProvider: openai,
    scope:        { userId },
  }),
});

const agent = new ToolLoopAgent({
  model:    registry.languageModel('nams:gpt-5.4-mini'),
  stopWhen: stepCountIs(1),
});
```

---

## Middleware Mode

Wrap any existing model instance with memory — useful when you already configure your model elsewhere and just want to decorate it:

```ts
import { createNams } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
} from 'ai';

const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const model = nams.wrap(openai('gpt-5.4-mini'), { userId: session.userId });

const agent = new ToolLoopAgent({ model, stopWhen: stepCountIs(1) });

const stream = createUIMessageStream({
  execute: async ({ writer }) => {
    const result = await agent.stream({ messages });
    writer.merge(result.toUIMessageStream());
  },
});

return createUIMessageStreamResponse({ stream });
```

---

## Tools Mode

Expose `query_memory` and `store_memory` as explicit AI SDK tools. The model decides when to call them, and the calls are visible in your UI — useful for debugging or when you want the user to see memory activity:

```ts
import { createNams } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';
import {
  ToolLoopAgent,
  createUIMessageStream,
  createUIMessageStreamResponse,
  stepCountIs,
} from 'ai';

const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const tools = nams.tools({ userId: session.userId });

const agent = new ToolLoopAgent({
  model:        openai('gpt-5.4-mini'),
  instructions: 'Always call query_memory first. Call store_memory after responding.',
  tools,
  stopWhen:     stepCountIs(10),
});

const stream = createUIMessageStream({
  execute: async ({ writer }) => {
    const result = await agent.stream({ messages });
    writer.merge(result.toUIMessageStream());
  },
});

return createUIMessageStreamResponse({ stream });
```

---

## Configuration

```ts
createNamsProvider({
  // Required
  apiKey:               string,
  baseProvider:         (modelId: string) => LanguageModelV3,
  scope:                { userId: string, conversationId?: string },

  // Optional
  endpoint?:            string,   // Default: https://memory.neo4jlabs.com/v1
  workspaceId?:         string,
  injectLimit?:         number,   // Max memories injected per turn. Default: 6
  persistInteractions?: boolean,  // Save each turn. Default: true
  extractionModel?:     LanguageModel, // Enables graph entity extraction
});
```

---

## Graph Extraction (optional)

Pass `extractionModel` to build a real Neo4j entity graph from memories instead of storing flat text:

```ts
const nams = createNamsProvider({
  apiKey:          process.env.MEMORY_API_KEY!,
  baseProvider:    openai,
  scope:           { userId },
  extractionModel: openai('gpt-5.4-mini'),
});
```

`"User is named Alex, works at TechCorp"` becomes `(Alex)-[:WORKS_AT]->(TechCorp)` in the graph.

---

## Memory Sources

NAMS searches four sources in parallel per turn:

| Source | What it stores |
|--------|---------------|
| Long-term graph | Facts, preferences, patterns (Neo4j entities + relationships) |
| Current conversation | Messages in the active session (vector search) |
| Cross-session | Messages from past conversations for the same user |
| Reasoning traces | Prior step-by-step reasoning from agent runs |

---

## Links

- [Neo4j Agent Memory Service](https://memory.neo4jlabs.com)
- [Vercel AI SDK community providers](https://ai-sdk.dev/providers/community-providers/custom-providers)
- [@neo4j-labs/agent-memory on npm](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Demo app + source](https://github.com/neo4j-labs/neo4j-agent-integrations/tree/main/vercel-agent/vercel_Nams)
