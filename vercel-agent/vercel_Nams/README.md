# NAMS Chat — Vercel AI SDK + Neo4j Agent Memory System

A production-ready Next.js chat application demonstrating **NAMS (Neo4j Agent Memory System)** integrated with the **Vercel AI SDK**. Serves as both a working example and a reusable template for building stateful AI agents that remember conversation context across sessions — with zero Neo4j infrastructure to manage.

**Key features:**
- **Two integration modes** — transparent provider middleware or explicit model-driven tools
- **Persistent memory** — long-term facts, user preferences, and interaction history stored in Neo4j
- **Cross-session retrieval** — agents recall information from previous conversations
- **Production patterns** — session management, error handling, streaming responses, reasoning traces
- **Portable** — copy `lib/nams/` to any Next.js + Vercel AI SDK project

---

## Quick Start

### Option A — Provider Mode (recommended)

Memory is retrieved and stored automatically on every turn. No system prompt changes needed.

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/vercel-agent/vercel_Nams
npm install
cp .env.local.example .env.local
# Edit .env.local: set MEMORY_API_KEY, OPENAI_API_KEY
npm run dev
# Open http://localhost:3000
```

```typescript
import { createNams } from '@/lib/nams';
import { streamText }  from 'ai';
import { openai }      from '@ai-sdk/openai';

const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const model = nams.wrap(openai('gpt-4o-mini'), { userId: 'user-123' });

const result = streamText({ model, messages });
```

### Option B — Tools Mode

The model decides when to call `query_memory` / `store_memory`. Tool calls are visible in the reasoning panel.

```bash
# Same setup, but set: NAMS_MODE=tools in .env.local
```

```typescript
import { createNams }   from '@/lib/nams';
import { SYSTEM_PROMPT } from '@/lib/constants';
import { streamText, stepCountIs } from 'ai';
import { openai } from '@ai-sdk/openai';

const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const tools = nams.tools({ userId: 'user-123' });

const result = streamText({
  model:    openai('gpt-4o-mini'),
  messages,
  tools,
  system:   SYSTEM_PROMPT,   // instructs: query → answer → store
  stopWhen: stepCountIs(10),
});
```

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│  Browser (Next.js / React)                                        │
│                                                                   │
│  ChatComponent (useChat + DefaultChatTransport)                   │
│    • sessionId from localStorage (key: nams-session-id)           │
│    • POST /api/chat  { messages, sessionId, conversationId? }     │
│    • GET  /api/reasoning?userId=&conversationId=                  │
│                                                                   │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐   │
│  │  Memory Panel        │  │  Reasoning Trace Panel           │   │
│  │  recent/ observations│  │  step 1 → step 2 → … → step N    │   │
│  │  reasoning tab       │  │  reasoning / action / result     │   │
│  └──────────────────────┘  └──────────────────────────────────┘   │
└───────────────────────────┬───────────────────────────────────────┘
                            │  HTTP streaming (NDJSON)
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  Next.js API Routes (Node.js runtime)                              │
│                                                                    │
│  POST /api/chat                    GET /api/reasoning              │
│  ─────────────────────────────     ─────────────────────────────   │
│  1. Parse UIMessages + sessionId   1. Look up userId → convId     │
│  2. Create / resume conversation   2. client.reasoning.listSteps() │
│  3. createNams().wrap() or .tools()│  3. Return step array as JSON │
│  4. streamText (OpenAI model)      │                               │
│  5. onFinish → recordStep          │                               │
│                                                                    │
└───────────────────────────┬────────────────────────────────────────┘
                            │  HTTPS REST
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  NAMS  —  https://memory.neo4jlabs.com/v1                          │
│  (@neo4j-labs/agent-memory SDK, backed by Neo4j AuraDB)            │
│                                                                    │
│  ┌──────────────────┐  ┌───────────────────┐  ┌────────────────┐  │
│  │  Short-Term      │  │  Long-Term        │  │  Reasoning     │  │
│  │  (conversation)  │  │  (graph entities) │  │  (step records)│  │
│  │                  │  │                   │  │                │  │
│  │  • vector search │  │  • facts          │  │  • reasoning   │  │
│  │  • per convId    │  │  • user_prefs     │  │  • actionTaken │  │
│  │  • cross-session │  │  • patterns       │  │  • result      │  │
│  └──────────────────┘  └───────────────────┘  └────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

### Memory flow per turn (Tools mode)

```
User sends message
      │
      ▼
[tool] query_memory ──────────────────────────────────────────────┐
      │  searches in parallel:                                     │
      │  • current conversation  (short-term, vector search)      │
      │  • past conversations    (cross-session, same userId)      │
      │  • long-term graph       (entities, facts, preferences)    │
      │  • prior reasoning steps                                   │
      │◄── returns ranked MemoryHit[] ─────────────────────────────┘
      │
      ▼
LLM composes personalised answer
      │
      ▼
[tool] store_memory
      │  routes by type:
      │  interaction   → short-term conversation thread
      │  fact          → long-term graph entity
      │  user_pref     → long-term graph entity
      │  pattern       → long-term graph entity
      ▼
onFinish callback → recordStep (reasoning trace)
      │
      ▼
Response streams to browser
```

---

## Integration Modes

Both modes use the same Neo4j backend. Choose based on your control-flow preference:

| Mode | Style | Visibility | Analogy |
|------|-------|------------|---------|
| **Provider** | Automatic, every turn | Invisible to caller | Mem0 / Letta |
| **Custom Tools** | Model-driven | Tool calls visible in UI | Supermemory / OpenAI Assistants |

```env
# .env.local
NAMS_MODE=provider   # (default) automatic memory via LanguageModelV3Middleware
# NAMS_MODE=tools    # model calls query_memory / store_memory explicitly
```

---

### Mode 1 — Provider (Transparent Middleware)

`createNams().wrap(model, scope)` returns a `LanguageModel` whose behaviour is identical to the original model, but with a `LanguageModelV3Middleware` inserted. Memory retrieval happens in `transformParams` before the model sees the prompt; persistence happens after the response via `wrapStream` / `wrapGenerate`.

```typescript
// app/api/chat/route.ts
import { createNams } from '@/lib/nams';
import { openai }     from '@ai-sdk/openai';
import { streamText, createUIMessageStream, createUIMessageStreamResponse } from 'ai';

export async function POST(req: Request) {
  const { messages, sessionId, conversationId } = await req.json();

  const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
  const model = nams.wrap(openai('gpt-4o-mini'), {
    userId: sessionId,       // sessionId from localStorage acts as userId
    conversationId,          // optional: pin to a specific conversation
  });

  const stream = createUIMessageStream({
    execute: ({ writer }) => {
      const result = streamText({ model, messages });
      writer.merge(result.toUIMessageStream());
    },
  });

  return createUIMessageStreamResponse({ stream });
}
```

What happens automatically on each request:

1. NAMS retrieves memories relevant to the user's last message (4 sources in parallel)
2. Memories are injected as context into the last user message before the model call
3. After the model responds, the turn is persisted to short-term memory

---

### Mode 2 — Custom Tools (Model-Driven)

`createNams().tools(scope)` returns `{ query_memory, store_memory }` as Vercel AI SDK `tool()` objects. Pass them to `streamText({ tools })` along with a system prompt that instructs the mandatory sequence.

```typescript
// app/api/chat/route.ts
import { createNams }    from '@/lib/nams';
import { SYSTEM_PROMPT } from '@/lib/constants';
import { openai }        from '@ai-sdk/openai';
import { streamText, stepCountIs, createUIMessageStream, createUIMessageStreamResponse } from 'ai';

export async function POST(req: Request) {
  const { messages, sessionId, conversationId } = await req.json();

  const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
  const tools = nams.tools({ userId: sessionId, conversationId });

  const stream = createUIMessageStream({
    execute: ({ writer }) => {
      const result = streamText({
        model:    openai('gpt-4o-mini'),
        messages,
        system:   SYSTEM_PROMPT,        // instructs: query → answer → store
        tools,
        stopWhen: stepCountIs(10),      // guard against runaway loops
      });
      writer.merge(result.toUIMessageStream());
    },
  });

  return createUIMessageStreamResponse({ stream });
}
```

The system prompt enforces a mandatory cycle every turn:

```
STEP 1 — query_memory (ALWAYS first):   retrieve context before answering
STEP 2 — answer the user:               use retrieved memories to personalise
STEP 3 — store_memory (ALWAYS after):   persist new facts, preferences, interactions
```

See [lib/constants.ts](lib/constants.ts) for the full system prompt.

---

### Mode 3 — Wrap an Entire Provider (Advanced)

`lib/nams-provider.ts` uses `wrapProvider` from the Vercel AI SDK so every model a provider returns inherits NAMS memory. This is the deepest SDK-level integration.

```typescript
import { createNamsProvider } from '@/lib/nams-provider';
import { openai }             from '@ai-sdk/openai';

const namsProvider = createNamsProvider({ apiKey, userId: 'user-123' });

// Wrap a single model
streamText({ model: namsProvider.wrapModel(openai('gpt-4o-mini')), ... });

// Or wrap the whole provider — every model from it has NAMS baked in
const memOpenAI = namsProvider.wrapProvider(openai);
streamText({ model: memOpenAI('gpt-4o-mini'), ... });
```

---

## Project Structure

```
vercel_Nams/
│
├── lib/
│   ├── nams/                      ← Portable NAMS integration (copy to your project)
│   │   ├── index.ts               ← createNams() — unified entry point
│   │   ├── provider.ts            ← Mode 1: LanguageModelV3Middleware (transparent)
│   │   ├── tools.ts               ← Mode 2: query_memory / store_memory tool() objects
│   │   ├── client.ts              ← MemoryClient helpers, retrieval, storage logic
│   │   └── extract.ts             ← LLM-backed graph entity extraction
│   │
│   ├── nams-memory-provider.ts    ← Full tools implementation used by Mode 3 + reasoning route
│   ├── nams-provider.ts           ← Mode 3: wrapModel() / wrapProvider() using wrapProvider SDK API
│   └── constants.ts               ← SYSTEM_PROMPT for tools mode
│
├── app/
│   ├── api/
│   │   ├── chat/route.ts          ← POST /api/chat — main agentic endpoint
│   │   └── reasoning/route.ts     ← GET  /api/reasoning — fetch stored reasoning steps
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx
│
├── components/
│   ├── AppHeader.tsx              ← Top bar
│   └── chat/
│       ├── ChatComponent.tsx      ← useChat, streaming, tool-call display
│       ├── MemoryPanel.tsx        ← Retrieved memories display (3 tabs)
│       ├── ReasoningPanel.tsx     ← Per-step reasoning trace
│       └── styles.ts              ← Shared inline style helpers
│
├── types/index.ts                 ← MemoryHit, ReasoningStep, etc.
├── utils/message.ts               ← getMsgText, parseMemory helpers
├── constants.ts                   ← DEFAULT_SUGGESTIONS, SESSION_STORAGE_KEY
├── .env.local.example
├── package.json
└── next.config.js
```

**Key insight:** The entire portable NAMS integration lives in `lib/nams/`. Copy that folder plus install two packages and you have persistent memory in any Vercel AI SDK project.

---

## Setup

### 1. Install dependencies

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/vercel-agent/vercel_Nams
npm install
```

### 2. Configure environment

```bash
cp .env.local.example .env.local
```

Edit `.env.local`:

```env
# Required
MEMORY_API_KEY=sk-nams-...     # Free key from https://memory.neo4jlabs.com
OPENAI_API_KEY=sk-proj-...

# Optional
NAMS_MODE=provider             # or "tools"
MEMORY_WORKSPACE_ID=           # leave blank for default workspace
MEMORY_ENDPOINT=               # override NAMS REST endpoint (rarely needed)
OPENAI_MODEL=gpt-4o-mini       # or gpt-4o for better tool-call reliability
```

### 3. Run

```bash
npm run dev
# Open http://localhost:3000
```

---

## Testing Memory

### Provider mode (`NAMS_MODE=provider`)

1. Send: *"My name is Alex and I prefer TypeScript over Python."*
   - Server logs show `[nams] created conversation` and `[nams] persist failed` (or no error)
   - The model replies naturally — no tool calls in the UI

2. Refresh the page (new browser session, same `userId` in `localStorage`)

3. Send: *"What language do I prefer?"*
   - Server logs show `[nams] resumed conversation` then retrieved memories
   - Model answers with TypeScript without being told again

### Tools mode (`NAMS_MODE=tools`)

1. Restart with `NAMS_MODE=tools`

2. Send: *"My favourite database is Neo4j."*
   - Reasoning panel shows `query_memory` called first, then `store_memory` after
   - Server logs: `[NAMS:store] fact (conf=0.9): "User's favourite database is Neo4j"`

3. Send: *"Which database do I prefer?"*
   - `query_memory` returns `found: true` with the stored fact
   - Model answers from memory, then calls `store_memory` again

### Inspect reasoning steps

```bash
curl "http://localhost:3000/api/reasoning?userId=<your-session-id>"
```

---

## Extracting NAMS for Your Project

Copy `lib/nams/` to your Next.js project:

```bash
cp -r vercel-agent/vercel_Nams/lib/nams /your-project/lib/
```

Install the required packages:

```bash
npm install @neo4j-labs/agent-memory ai zod
```

Then pick a mode:

```typescript
import { createNams } from '@/lib/nams';

// Provider mode — simplest, transparent
const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const model = nams.wrap(openai('gpt-4o-mini'), { userId });
return streamText({ model, messages }).toUIMessageStreamResponse();
```

```typescript
// Tools mode — model-driven, visible in UI
const tools = nams.tools({ userId });
return streamText({
  model: openai('gpt-4o-mini'),
  messages,
  tools,
  system: SYSTEM_PROMPT,
  stopWhen: stepCountIs(10),
}).toUIMessageStreamResponse();
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_API_KEY` | Yes | — | API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `NAMS_MODE` | No | `provider` | `provider` (transparent) or `tools` (model-driven) |
| `MEMORY_WORKSPACE_ID` | No | _(default workspace)_ | Pin to a specific NAMS workspace |
| `MEMORY_ENDPOINT` | No | `https://memory.neo4jlabs.com/v1` | Override NAMS REST endpoint |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | LLM model ID |

---

## Dependencies

| Package | Role |
|---------|------|
| `ai` (Vercel AI SDK v6) | `streamText`, `tool`, `wrapLanguageModel`, `createUIMessageStream`, `useChat` |
| `@ai-sdk/openai` | OpenAI model provider |
| `@ai-sdk/react` | `useChat` React hook |
| `@neo4j-labs/agent-memory` | NAMS `MemoryClient` — short-term, long-term, reasoning REST APIs |
| `@neo4j-ndl/react` | Neo4j Design Language UI components |
| `zod` | Input schema validation for memory tools |
| `next` | App framework and API routes |

---

## Troubleshooting

**Memory not persisting across sessions**
- Verify `userId` is stable across requests — the app reads `localStorage.getItem('nams-session-id')` and sends it as `sessionId`
- In tools mode: confirm server logs show `[NAMS:store]` entries
- Check `MEMORY_API_KEY` is set and valid

**Model never calls memory tools (tools mode)**
- Verify `NAMS_MODE=tools` is set
- Use `gpt-4o` instead of `gpt-4o-mini` for better tool-call reliability
- Check server logs to confirm tools are being registered

**HTTP 503 / MEMORY_API_KEY errors**
- Generate a free key at [memory.neo4jlabs.com](https://memory.neo4jlabs.com)
- Restart the dev server after updating `.env.local`

---

## Resources

- [Neo4j Agent Memory Service](https://memory.neo4jlabs.com)
- [Vercel AI SDK — agents and memory](https://sdk.vercel.ai/docs/agents/memory)
- [Vercel AI SDK — wrapLanguageModel](https://sdk.vercel.ai/docs/reference/ai-sdk-core/wrap-language-model)
- [@neo4j-labs/agent-memory on npm](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Source code — neo4j-agent-integrations](https://github.com/neo4j-labs/neo4j-agent-integrations/tree/main/vercel-agent)
