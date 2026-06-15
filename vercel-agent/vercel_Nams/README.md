# NAMS Chat — Vercel AI SDK + Neo4j Agent Memory System

A Next.js chat application that wires **NAMS (Neo4j Agent Memory System)** into the **Vercel AI SDK** as a pair of tools (`query_memory` / `store_memory`). Every conversation is stored in a Neo4j graph; the agent retrieves relevant context before answering and persists new knowledge after each reply — across sessions.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser (Next.js)                              │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  components/chat/ChatComponent.tsx  (useChat + DefaultChatTransport)│   │
│  │                                                                     │   │
│  │  • Generates a stable sessionId (localStorage key: nams-session-id) │   │
│  │  • Sends messages → POST /api/chat  {sessionId, conversationId}     │   │
│  │  • Receives streaming UIMessage parts + data-conversation-id event  │   │
│  │  • Fetches GET /api/reasoning?userId=&conversationId= after reply   │   │
│  │                                                                     │   │
│  │  ┌──────────────────────┐  ┌────────────────────────────────────┐  │   │
│  │  │   Agent Memory panel │  │        Reasoning Trace panel       │  │   │
│  │  │  recent │ observations│  │  step 1 → step 2 → step N         │  │   │
│  │  │         │ reasoning   │  │  reasoning / action / result      │  │   │
│  │  └──────────────────────┘  └────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │  HTTP (streaming NDJSON)
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Next.js API Routes (Node.js)                        │
│                                                                             │
│  POST /api/chat                          GET /api/reasoning                 │
│  ─────────────────────────────────────   ─────────────────────────────      │
│  1. Parse UIMessages + session IDs       1. Look up userId → convId         │
│  2. getOrCreateConversation (NAMS)       2. client.reasoning.listSteps()    │
│  3. addMessage (user turn)               3. Return step array as JSON       │
│  4. createNamsMemoryTools()                                                  │
│  5. streamText (OpenAI model)                                                │
│     ├─ system prompt: mandatory          ┌──────────────────────────────┐   │
│     │  query → answer → store cycle      │  NAMS Memory Tools (Vercel)  │   │
│     └─ tools ──────────────────────────▶│  query_memory / store_memory │   │
│  6. onFinish:                            └──────────────┬───────────────┘   │
│     ├─ addMessage (assistant turn)                      │                   │
│     └─ recordStep (reasoning trace)                     │                   │
└─────────────────────────────────────────────────────────┼───────────────────┘
                                                          │  HTTPS REST
                                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NAMS  —  https://memory.neo4jlabs.com/v1                 │
│                    (@neo4j-labs/agent-memory SDK)                           │
│                                                                             │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │   Short-Term Memory  │  │   Long-Term Memory   │  │  Reasoning Trace │  │
│  │  (conversation msgs) │  │  (graph entities)    │  │  (step records)  │  │
│  │                      │  │                      │  │                  │  │
│  │ • scoped per convId  │  │ • facts              │  │ • reasoning text │  │
│  │ • vector search      │  │ • user_preferences   │  │ • actionTaken    │  │
│  │ • cross-session scan │  │ • patterns           │  │ • result summary │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
│                                                                             │
│                    Backed by a Neo4j AuraDB graph                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Memory flow per turn

```
User sends message
       │
       ▼
 [tool] query_memory ──────────────────────────────────────────┐
       │  searches:                                             │
       │  • current conversation (short-term, vector)          │
       │  • past conversations for this userId (cross-session) │
       │  • long-term graph entities                           │
       │  • prior reasoning steps                              │
       │◀──────────── returns ranked MemoryHit[] ──────────────┘
       │
       ▼
 LLM composes answer  (personalised with retrieved context)
       │
       ▼
 [tool] store_memory
       │  persists:
       │  • interaction  → short-term conversation thread
       │  • fact         → long-term graph entity
       │  • user_preference → long-term graph entity
       │  • pattern      → long-term graph entity
       │
       ▼
 onFinish callback
       │  • addMessage (assistant turn) → short-term
       │  • recordStep (reasoning)      → reasoning trace
       ▼
 Response streams to browser
```

---

## Using NAMS as a Vercel AI SDK Memory Provider

NAMS ships a `NamsMemoryProvider` class that follows the same pattern as [Mem0](https://mem0.ai), [Letta](https://letta.com), and [Supermemory](https://supermemory.ai) — the providers listed in the [Vercel AI SDK memory docs](https://ai-sdk.dev/docs/agents/memory).

### Minimal integration (3 lines)

```typescript
import { NamsMemoryProvider } from '@/lib/nams-memory-provider';
import { streamText } from 'ai';
import { openai } from '@ai-sdk/openai';

// 1. Create a shared provider instance (once at module level)
const memory = new NamsMemoryProvider({
  apiKey: process.env.MEMORY_API_KEY!,
  userId: 'default',                       // overridden per-request with forUser()
});

// 2. Scope it to the current user and pass tools to streamText
const result = streamText({
  model:    openai('gpt-4o-mini'),
  system:   SYSTEM_PROMPT,
  messages,
  tools:    memory.forUser(userId).tools(),   // ← drops in alongside any other tools
});
```

`forUser(userId, conversationId?)` returns a new provider scoped to that user — safe to call on every request with no shared state between users.

### Provider API surface

```typescript
// lib/nams-memory-provider.ts

class NamsMemoryProvider {
  constructor(opts: {
    apiKey:        string;
    userId:        string;
    workspaceId?:  string;
    endpoint?:     string;
    conversationId?: string;
  })

  /** Scope to a specific user per-request (returns a new provider, no mutation). */
  forUser(userId: string, conversationId?: string): NamsMemoryProvider

  /** Returns { query_memory, store_memory } ready to pass to streamText. */
  tools(): { query_memory: Tool; store_memory: Tool }
}
```

---

## Memory Design

### Approach — Hybrid "Custom Tools + Memory Provider"

The [Vercel AI SDK memory docs](https://ai-sdk.dev/docs/agents/memory) describe three implementation strategies:

| Strategy | Description |
|----------|-------------|
| **Provider-defined tools** | Provider ships the tool interface; you supply `execute` |
| **Memory Provider** | Third-party service (Mem0, Letta, Supermemory) handles storage transparently |
| **Custom Tool** | You own the full schema, execute logic, and storage backend |

NAMS implements the **Memory Provider** strategy: `NamsMemoryProvider` ships the complete tool interface (schema + execute logic + storage backend). Drop `memory.forUser(userId).tools()` into any `streamText` call and NAMS handles the rest.

- **Storage** — [`@neo4j-labs/agent-memory`](https://www.npmjs.com/package/@neo4j-labs/agent-memory) (NAMS) persists everything to a managed Neo4j AuraDB graph.
- **Tools** — two Vercel AI SDK `tool` objects (`query_memory` / `store_memory`) with hand-crafted schemas. The LLM is instructed to call them on every turn via `SYSTEM_PROMPT`.

This gives the agent **full control over what gets stored and at what confidence level**, while offloading the storage infrastructure to NAMS.

---

### Three Memory Layers

The implementation maps to three cognitive memory types:

| Layer | Cognitive type | Storage | Retrieval |
|-------|---------------|---------|-----------|
| **Short-term** | Episodic | Per-conversation message thread in NAMS | Vector similarity search (`threshold ≥ 0.4`) |
| **Long-term** | Semantic | Neo4j graph entities (facts, preferences, patterns) | Graph entity search |
| **Reasoning trace** | Procedural | Per-step records (reasoning text + action taken + result) | Listed per conversation |

Cross-session retrieval bridges short-term and long-term: `query_memory` also scans all past conversations for the same `userId`, so facts told in a previous session are available in the next one without being explicitly promoted to the long-term graph.

---

### Mandatory Memory Cycle

The agent is constrained by `SYSTEM_PROMPT` (`lib/constants.ts`) to follow this sequence on every single turn — no exceptions:

```
STEP 1  query_memory   → retrieve context BEFORE answering
STEP 2  answer         → respond using retrieved memories as grounding
STEP 3  store_memory   → persist new facts/preferences/interactions AFTER answering
```

This is an **agent-directed** (not automatic) memory pattern: the LLM decides what is worth storing, what confidence to assign, and how to classify the content (`fact` / `user_preference` / `interaction` / `pattern`).

---

### Transport — REST API, Not Direct Neo4j

The `MemoryClient` from `@neo4j-labs/agent-memory` is a thin **HTTPS REST client**. It does not connect directly to Neo4j. Every operation becomes a `POST` to the NAMS cloud API:

```
App  ──HTTPS POST──▶  https://memory.neo4jlabs.com/v1/<method>  ──▶  Neo4j AuraDB
```

Authentication is via the `MEMORY_API_KEY` header. The `makeClient` helper in [lib/nams-memory-provider.ts](lib/nams-memory-provider.ts) constructs this client:

```typescript
new MemoryClient({
  endpoint: 'https://memory.neo4jlabs.com/v1',
  apiKey:   process.env.MEMORY_API_KEY,
  headers:  { 'X-Workspace-ID': process.env.MEMORY_WORKSPACE_ID },
})
```

Each `client.shortTerm.*`, `client.longTerm.*`, and `client.reasoning.*` call translates to a separate REST request.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Node.js | ≥ 18 | Required for `crypto.randomUUID` and `fetch` |
| npm | ≥ 9 | Bundled with Node 18+ |
| NAMS API key | — | Free at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| OpenAI API key | — | Used for the LLM (`gpt-4o-mini` by default) |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/vercel-agent/vercel_Nams
npm install
```

### 2. Configure environment variables

Copy the example file and fill in your keys:

```bash
cp .env.local.example .env.local
```

Edit `.env.local`:

```env
# Required — get a free key at https://memory.neo4jlabs.com
MEMORY_API_KEY=your-nams-api-key

# Optional — pin to a specific NAMS workspace (leave blank for default)
MEMORY_WORKSPACE_ID=

# Optional — override the NAMS endpoint
# MEMORY_ENDPOINT=https://memory.neo4jlabs.com/v1

# Required — your OpenAI API key
OPENAI_API_KEY=sk-...

# Optional — override the model (default: gpt-4o-mini)
# OPENAI_MODEL=gpt-4o
```

---

## Running

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The app starts with four built-in suggestion prompts to illustrate the memory cycle. Click one or type your own message.

### Production build

```bash
npm run build
npm start
```

---

## Project structure

```
vercel_Nams/
├── app/
│   ├── api/
│   │   ├── chat/route.ts          # POST /api/chat — main agent endpoint
│   │   └── reasoning/route.ts     # GET  /api/reasoning — fetch stored steps
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx                   # Root page — wires AppHeader + ChatComponent
├── components/
│   ├── AppHeader.tsx              # Top bar with dark/light toggle
│   └── chat/
│       ├── ChatComponent.tsx      # Chat UI — useChat, tool-call display, panels
│       ├── MemoryPanel.tsx        # Collapsible panel: recent / observations / reasoning tabs
│       ├── ReasoningPanel.tsx     # Per-message reasoning step trace
│       └── styles.ts              # Shared inline style helpers
├── lib/
│   ├── constants.ts               # SYSTEM_PROMPT (mandatory query→answer→store)
│   └── nams-memory-provider.ts    # NAMS client, tools, conversation helpers
├── types/
│   └── index.ts                   # Shared TypeScript types (MemoryHit, ReasoningStep, …)
├── utils/
│   └── message.ts                 # getMsgText, parseMemory, formatErrorMessage helpers
├── constants.ts                   # DEFAULT_SUGGESTIONS, SESSION_STORAGE_KEY
├── declarations.d.ts              # Module augmentations / ambient declarations
├── .env.local.example
└── package.json
```

---

## Key files explained

### `lib/nams-memory-provider.ts`

The core integration layer. Exports:

| Export | Purpose |
|--------|---------|
| `getOrCreateConversation(opts)` | Resolves (or creates) a NAMS conversation for a userId. Caches the result in-process. |
| `findExistingConversation(opts)` | Read-only lookup — never creates. Used by the reasoning endpoint. |
| `createNamsMemoryTools(opts)` | Returns `{ query_memory, store_memory }` — Vercel AI SDK `tool` objects ready to pass to `streamText`. |

**`query_memory`** — searches four sources in parallel:
- Short-term messages in the current conversation (vector similarity ≥ 0.4)
- Past conversations for the same userId (cross-session, threshold 0.45)
- Long-term graph entities
- Prior reasoning steps

**`store_memory`** — routes by `type`:
- `interaction` → `client.shortTerm.addMessage` (conversation thread)
- `fact` / `user_preference` / `pattern` → `client.longTerm.addEntity` (graph node)

### `app/api/chat/route.ts`

The POST handler that runs the agentic loop:

1. Parses `messages`, `sessionId`, `userId`, `conversationId` from the request body.
2. Calls `getOrCreateConversation` to get a stable NAMS `convId`.
3. Ingests the user message to short-term memory (fire-and-forget).
4. Passes `createNamsMemoryTools(...)` to `streamText` with up to 10 agentic steps.
5. In `onFinish`: persists the assistant reply and records each reasoning step to NAMS.
6. Sends the NAMS `convId` back to the client via a custom `data-conversation-id` stream event.

### `lib/constants.ts`

Defines `SYSTEM_PROMPT`, which enforces the mandatory three-step cycle every turn:

```
STEP 1  query_memory   (always before answering)
STEP 2  answer the user
STEP 3  store_memory   (always after answering)
```

### `components/chat/ChatComponent.tsx`

React component built on `useChat` (`@ai-sdk/react`) with `DefaultChatTransport` (`ai`). Sends `sessionId` and the resolved `conversationId` on every request. Reads the `data-conversation-id` stream event to pin subsequent requests to the same NAMS conversation. Renders:

- **Agent Memory panel** (`MemoryPanel.tsx`) — collapsible, tabbed view of what NAMS returned (`recent` / `observations` / `reasoning`).
- **Reasoning Trace panel** (`ReasoningPanel.tsx`) — steps fetched from `/api/reasoning` after each reply, showing reasoning text, action taken, and result summary.
- Live tool-call status while streaming.

---

## Testing

### Manual smoke test (recommended first run)

1. Start the dev server: `npm run dev`
2. Open [http://localhost:3000](http://localhost:3000)
3. Click **"Hi! I'm Alex, a data scientist at TechCorp."**
   - The Agent Memory panel should show `0 recent` on the first message (no prior memories yet).
   - After the reply, expand the Reasoning Trace to see the stored step.
4. Click **"What do you remember about me?"**
   - The Agent Memory panel should now show recalled facts about you from the previous turn.
   - This confirms the store → retrieve cycle is working end-to-end.

### Verifying memory persistence across sessions

1. Send a few messages, then close the browser tab.
2. Reopen [http://localhost:3000](http://localhost:3000) in a new tab.
3. Ask **"What do you remember about me?"**
   - The agent should recall information from the previous session via cross-session search.
   - Your `userId` is persisted in `localStorage` under the key `nams-session-id`.

### Server-side logs

The server logs a detailed trace for every request. Watch the terminal for:

```
══════════════════════════════════════════════
[chat] ① POST /api/chat
[chat]   session: <id> | userId: <id> | existingConv: none
[chat]   query: "Hi! I'm Alex..."
[NAMS] New conversation → <convId> for userId=<id> (42ms)
[chat] ② Conversation resolved: <convId>
[chat] ③ Agent | model: gpt-4o-mini | maxSteps: 10
[NAMS:query] "Hi Alex data scientist TechCorp" (limit=5)
[NAMS:query] ✓ 0 current + 0 cross-session + 0 long-term + 0 reasoning (130ms)
[NAMS:store] fact (conf=0.85): "User is named Alex, works as a data scientist..."
[NAMS:store] ✓ long-term "User is named Alex, works as a data scientist..." (90ms)
[chat] ④ Done | steps: 3 | 🔍 ×1 | 💾 ×1 | 1240ms
[chat]   tokens: input=412 output=87
```

### API endpoints

```bash
# Health-check: fetch reasoning steps for a userId
curl "http://localhost:3000/api/reasoning?userId=<your-nams-session-id>"

# Expected response (no steps yet):
# {"steps":[]}
```

---

## Environment variables reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_API_KEY` | Yes | — | NAMS API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| `MEMORY_WORKSPACE_ID` | No | _(default workspace)_ | Pin to a specific NAMS workspace |
| `MEMORY_ENDPOINT` | No | `https://memory.neo4jlabs.com/v1` | Override the NAMS API base URL |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | Model ID passed to `openai()` |

---

## Dependencies

| Package | Role |
|---------|------|
| `ai` (Vercel AI SDK) | `streamText`, `tool`, `useChat`, `createUIMessageStream` |
| `@ai-sdk/openai` | OpenAI provider for the Vercel AI SDK |
| `@ai-sdk/react` | `useChat` React hook |
| `@neo4j-labs/agent-memory` | NAMS `MemoryClient` — short-term, long-term, reasoning APIs |
| `@neo4j-ndl/react` | Neo4j Design Language UI components |
| `zod` | Input schema validation for the memory tools |
| `next` | App framework and API routes |

---

## How NAMS is used as a tool

NAMS is not called directly by the application logic — it is exposed to the LLM as two Vercel AI SDK `tool` objects. The model decides when to call them, guided by `SYSTEM_PROMPT`.

```typescript
// lib/nams-memory-provider.ts
export function createNamsMemoryTools(options: NamsMemoryOptions) {
  // ...
  const query_memory = tool({ description: '...', inputSchema: zodSchema(querySchema), execute: async ({ query, limit }) => { /* searches NAMS */ } });
  const store_memory = tool({ description: '...', inputSchema: zodSchema(storeSchema), execute: async ({ content, type, confidence }) => { /* writes to NAMS */ } });
  return { query_memory, store_memory };
}

// app/api/chat/route.ts
const tools = createNamsMemoryTools(memoryOptions);
const result = streamText({ model: openai(model), system: SYSTEM_PROMPT, messages, tools, stopWhen: stepCountIs(10) });
```

This pattern keeps NAMS entirely in the tool layer — the model orchestrates when memory is read and written, while the application code only defines the interface.
