# NAMS Chat — Vercel AI SDK + Neo4j Agent Memory System

A production-ready Next.js chat application demonstrating **NAMS (Neo4j Agent Memory System)** integrated with the **Vercel AI SDK**. Serves as both a working example and a reference client for the [`@neo4j-labs/nams-ai-provider`](../nams-provider) package — persistent memory backed by Neo4j with zero infrastructure to manage.

**Key features:**
- **Two memory integration modes** — transparent provider middleware or explicit model-driven tools
- **Live database access** — optional Neo4j MCP server integration for real-time graph queries
- **Persistent cross-session memory** — facts, preferences, and interaction history recalled across page reloads
- **Reasoning trace** — per-step tool-call record stored and surfaced in the UI
- **Portable** — all NAMS memory logic lives in `@neo4j-labs/nams-ai-provider`; drop it into any Vercel AI SDK project

---

## Quick Start

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/vercel-agent/vercel_Nams
npm install
cp .env.local.example .env.local
# Edit .env.local: set MEMORY_API_KEY and OPENAI_API_KEY at minimum
npm run dev
# Open http://localhost:3000
```

### Option A — Provider Mode (default, recommended)

Memory is retrieved and stored automatically on every turn. No system prompt changes needed.

```env
NAMS_MODE=provider
```

```typescript
import { createNamsProvider } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';

const nams  = createNamsProvider({
  apiKey:       process.env.MEMORY_API_KEY!,
  baseProvider: openai,
  scope:        { userId: 'user-123' },
});

// Memory is injected/persisted transparently — drop-in model replacement
const model = nams.languageModel('gpt-4o-mini');
```

### Option B — Tools Mode

The model decides when to call `query_memory` / `store_memory`. Tool calls (and any Neo4j MCP calls) are visible in the reasoning panel.

```env
NAMS_MODE=tools
```

```typescript
import { createNams } from '@neo4j-labs/nams-ai-provider';

const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });

// NAMS memory tools + optional MCP tools merged in one call
const { tools, close } = await nams.toolsWithMcp(
  { userId: 'user-123' },
  mcpConfig,   // { url, headers } — omit to skip MCP
);

// pass tools to ToolLoopAgent; call close() in onFinish
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
│  │  recent observations │  │  step 1 → step 2 → … → step N   │   │
│  │  reasoning tab       │  │  reasoning / action / result     │   │
│  └──────────────────────┘  └──────────────────────────────────┘   │
└───────────────────────┬───────────────────────────────────────────┘
                        │  HTTP streaming (NDJSON)
                        ▼
┌────────────────────────────────────────────────────────────────────┐
│  Next.js API Routes (Node.js runtime)                              │
│                                                                    │
│  POST /api/chat                      GET /api/reasoning            │
│  ───────────────────────────────     ─────────────────────────     │
│  1. Parse UIMessages + sessionId     1. userId → convId lookup     │
│  2. Create / resume conversation     2. client.reasoning.listSteps │
│  3. Provider mode  OR  tools mode    3. Return step array as JSON  │
│  4. ToolLoopAgent streams response                                 │
│  5. onFinish → recordStep                                          │
│                                                                    │
└───────────────────────┬────────────────────────────────────────────┘
                        │  HTTPS REST
                        ▼
┌────────────────────────────────────────────────────────────────────┐
│  NAMS  —  https://memory.neo4jlabs.com/v1                          │
│  (@neo4j-labs/agent-memory SDK, backed by Neo4j AuraDB)            │
│                                                                    │
│  ┌──────────────────┐  ┌───────────────────┐  ┌────────────────┐  │
│  │  Short-Term      │  │  Long-Term        │  │  Reasoning     │  │
│  │  (conversation)  │  │  (graph entities) │  │  (step records)│  │
│  │  • vector search │  │  • facts          │  │  • reasoning   │  │
│  │  • per convId    │  │  • user_prefs     │  │  • actionTaken │  │
│  │  • cross-session │  │  • patterns       │  │  • result      │  │
│  └──────────────────┘  └───────────────────┘  └────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## Integration Modes

Both modes use the same Neo4j backend and the same `@neo4j-labs/nams-ai-provider` package. Choose based on control-flow preference:

| Mode | Memory handling | MCP tools | Analogy |
|------|----------------|-----------|---------|
| **Provider** | Transparent middleware — model never sees memory tools | Added separately to `ToolLoopAgent` | Mem0 / Letta |
| **Tools** | `query_memory` + `store_memory` tool calls the model drives | Merged in via `toolsWithMcp()` — single `close()` | Supermemory |

```env
NAMS_MODE=provider   # (default) automatic memory via LanguageModelV3Middleware
NAMS_MODE=tools      # model calls query_memory / store_memory explicitly
```

---

### Mode 1 — Provider (Transparent Middleware)

`createNamsProvider()` returns a `ProviderV3`-compatible provider. Every `languageModel(id)` call resolves through the base provider (e.g. `openai`) and wraps the result with a `LanguageModelV3Middleware`. Memory retrieval is injected into the prompt in `transformParams`; persistence happens after the response.

```typescript
// app/api/chat/route.ts
import { createNamsProvider } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';
import { ToolLoopAgent, createUIMessageStream, createUIMessageStreamResponse, stepCountIs } from 'ai';

export async function POST(req: Request) {
  const { messages, sessionId } = await req.json();

  const nams  = createNamsProvider({
    apiKey:       process.env.MEMORY_API_KEY!,
    baseProvider: openai,
    scope:        { userId: sessionId },
  });

  const agent = new ToolLoopAgent({
    model:    nams.languageModel('gpt-4o-mini'),
    stopWhen: stepCountIs(1),
  });

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      writer.merge((await agent.stream({ messages })).toUIMessageStream());
    },
  });

  return createUIMessageStreamResponse({ stream });
}
```

What happens automatically on each request:
1. Memories relevant to the user's last message are retrieved (4 sources in parallel)
2. Retrieved memories are injected as context before the model call
3. The model's response is persisted to short-term memory after the turn

**MCP in provider mode:** MCP tools are connected separately and passed to `ToolLoopAgent`. Because `toolsWithMcp()` also emits `query_memory`/`store_memory` tools, it can't be used in provider mode — that would double-handle memory (middleware + explicit tools). Instead the route calls `getNeo4jMcpTools()` directly and merges only the MCP tools.

---

### Mode 2 — Tools (Model-Driven)

`createNams().toolsWithMcp()` returns `{ query_memory, store_memory }` merged with any Neo4j MCP tools in a single object. The model decides when to call each tool. A system prompt enforces the mandatory cycle.

```typescript
// app/api/chat/route.ts
import { createNams } from '@neo4j-labs/nams-ai-provider';
import { SYSTEM_PROMPT } from '@/lib/constants';
import { openai } from '@ai-sdk/openai';
import { ToolLoopAgent, createUIMessageStream, createUIMessageStreamResponse, stepCountIs } from 'ai';

export async function POST(req: Request) {
  const { messages, sessionId } = await req.json();

  const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });

  // One call — NAMS memory tools + Neo4j MCP tools merged; one close() covers both
  const { tools, close } = await nams.toolsWithMcp(
    { userId: sessionId },
    { url: process.env.MCP_URL!, headers: { Authorization: `Basic ${btoa('user:pass')}` } },
  );

  const agent = new ToolLoopAgent({
    model:        openai('gpt-4o-mini'),
    instructions: SYSTEM_PROMPT,
    tools,
    stopWhen:     stepCountIs(10),
    onFinish:     async () => { await close(); },
  });

  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      writer.merge((await agent.stream({ messages })).toUIMessageStream());
    },
  });

  return createUIMessageStreamResponse({ stream });
}
```

The system prompt enforces a mandatory cycle every turn:
```
STEP 1 — query_memory   retrieve context before answering
STEP 2 — answer         use retrieved memories to personalise
STEP 3 — store_memory   persist new facts, preferences, interactions
```

When MCP is not configured, `toolsWithMcp(scope)` (no second argument) returns NAMS memory tools only — the `close()` is a no-op.

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
[tool] read-cypher / get-schema (MCP — if configured)
      │  live Neo4j graph queries
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
onFinish → recordStep (reasoning trace) → close()
      │
      ▼
Response streams to browser
```

---

## Project Structure

```
vercel_Nams/
│
├── app/
│   ├── api/
│   │   ├── chat/route.ts          ← POST /api/chat — mode switching, ToolLoopAgent
│   │   └── reasoning/route.ts     ← GET  /api/reasoning — fetch stored reasoning steps
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx
│
├── components/
│   ├── AppHeader.tsx
│   └── chat/
│       ├── ChatComponent.tsx      ← useChat, streaming, tool-call display
│       ├── MemoryPanel.tsx        ← Retrieved memories display (3 tabs)
│       ├── ReasoningPanel.tsx     ← Per-step reasoning trace
│       └── styles.ts
│
├── lib/
│   ├── constants.ts               ← SYSTEM_PROMPT (tools mode) + NEO4J_MCP addendum
│   └── neo4j-mcp.ts               ← MCP client helper + getNamsMcpConfig()
│
├── types/index.ts                 ← MemoryHit, ReasoningStep, etc.
├── utils/message.ts               ← getMsgText, parseMemory helpers
├── constants.ts                   ← DEFAULT_SUGGESTIONS, SESSION_STORAGE_KEY
├── .env.local.example
├── package.json
└── next.config.js
```

**NAMS integration lives entirely in `@neo4j-labs/nams-ai-provider`** — installed as a package, not copied source. See [`../nams-provider`](../nams-provider) for the implementation.

---

## Testing the NAMS Provider (Developer Setup)

`vercel_Nams` is the **reference client** for `@neo4j-labs/nams-ai-provider`. It consumes the provider as a local `file:` dependency, so you can make changes to the provider source and test them here without publishing to npm.

### Step 1 — Build the provider

```bash
cd ../nams-provider        # from vercel_Nams/
npm install
npm run build              # outputs dist/ (JS + types)
```

You only need to rebuild when provider source changes. Run `npm run dev` in `nams-provider/` during active development to rebuild on every save.

### Step 2 — Install in vercel_Nams

`package.json` already has the local link:

```json
"@neo4j-labs/nams-ai-provider": "file:../nams-provider"
```

Install it (from `vercel_Nams/`):

```bash
npm install --legacy-peer-deps
```

Verify it resolved:

```bash
ls node_modules/@neo4j-labs/
# agent-memory   nams-ai-provider   ← both should appear
```

### Step 3 — Configure environment

```bash
cp .env.local.example .env.local
```

Set at minimum:

```env
MEMORY_API_KEY=nams_...
OPENAI_API_KEY=sk-proj-...
NAMS_MODE=tools            # start with tools mode — tool calls are visible in the UI
```

### Step 4 — Run the app

```bash
npm run dev
# Open http://localhost:3000
```

### Step 5 — Test each integration path

**Path A — Tools mode** (`NAMS_MODE=tools`, no MCP vars set)

Exercises `createNams().toolsWithMcp(scope)` — NAMS memory tools only.

```
Send: "My name is Alex and I like TypeScript"
→ Reasoning panel shows: query_memory → answer → store_memory
→ Server log: [nams:tools] store_memory — type=fact
→ Send again: "What language do I like?"
→ query_memory returns found=true; model answers from memory
```

**Path B — Tools mode + MCP** (set `MCP_URL`, `MCP_NEO4J_USERNAME`, `MCP_NEO4J_PASSWORD`)

Exercises `createNams().toolsWithMcp(scope, mcpConfig)` — NAMS + Neo4j tools merged.

```
Send: "What nodes are in my Neo4j database?"
→ Server log: [nams:tools] MCP connected — tools: get-schema, read-cypher, write-cypher
→ Server log: [chat] tools=5  (2 NAMS + 3 MCP)
→ Agent calls get-schema, then read-cypher, then stores findings in memory
```

**Path C — Provider mode** (`NAMS_MODE=provider`)

Exercises `createNamsProvider()` — transparent middleware, no visible tool calls.

```
Send: "My favourite colour is blue"
→ Server log: no query_memory / store_memory calls — memory is middleware-driven
→ Refresh the page; send: "What's my favourite colour?"
→ Model answers "blue" — retrieved transparently before the model call
```

### What to look for in server logs

| Log line | Confirms |
|---|---|
| `[nams:tools] createNamsMemoryTools` | Tools created by provider |
| `[nams:tools] MCP connected — tools: ...` | `toolsWithMcp` connected MCP successfully |
| `[chat] tools=N` | N tools registered (2 NAMS + N MCP) |
| `[nams:tools] query_memory — found N memories` | Memory retrieval working |
| `[nams:tools] store_memory — stored OK` | Memory persistence working |
| `[chat] Done \| queries=N stores=N elapsed=Xms` | Full turn summary |

### Rebuilding after provider changes

```bash
# In nams-provider/
npm run build

# In vercel_Nams/ — reinstall to pick up new dist/
npm install --legacy-peer-deps
```

Next.js picks up the rebuilt package on the next request without restarting the dev server.

---

## Using NAMS in Your Own Project

Install the package from npm:

```bash
npm install @neo4j-labs/nams-ai-provider @neo4j-labs/agent-memory ai zod
```

Pick a mode:

```typescript
import { createNamsProvider, createNams } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';

// Provider mode — simplest, transparent
const nams  = createNamsProvider({ apiKey, baseProvider: openai, scope: { userId } });
const model = nams.languageModel('gpt-4o-mini');

// Tools mode — model-driven, tool calls visible in UI
const { tools, close } = await createNams({ apiKey }).toolsWithMcp({ userId });
```

---

## Setup

### 1. Install dependencies

```bash
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
MEMORY_API_KEY=nams_...        # Free key from https://memory.neo4jlabs.com
OPENAI_API_KEY=sk-proj-...

# Integration mode
NAMS_MODE=provider             # provider (default) or tools

# Optional NAMS
MEMORY_WORKSPACE_ID=           # leave blank for default workspace
OPENAI_MODEL=gpt-4o-mini       # or gpt-4o for better tool-call reliability

# Optional MCP — connect to a live Neo4j database
MCP_URL=https://your-mcp-server/mcp
# MCP_PORT=8443                # alternative: local server on this port
MCP_NEO4J_USERNAME=
MCP_NEO4J_PASSWORD=
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
   - Server logs: `[nams] created conversation`, model replies with no visible tool calls

2. Refresh the page (new browser session, same `userId` from `localStorage`)

3. Send: *"What language do I prefer?"*
   - Server logs show memory retrieval; model answers *TypeScript* without being told again

### Tools mode (`NAMS_MODE=tools`)

1. Send: *"My favourite database is Neo4j."*
   - Reasoning panel: `query_memory` called first, then `store_memory` after
   - Server logs: `[nams:tools] store_memory — type=fact`

2. Send: *"Which database do I prefer?"*
   - `query_memory` returns `found: true`; model answers from memory, then stores again

### Tools mode + MCP (`NAMS_MODE=tools` + MCP vars set)

1. Send: *"What nodes are in my Neo4j database?"*
   - Agent calls `get-schema` or `read-cypher` via MCP, then stores findings in memory
   - `tools=N` in server log shows NAMS tools (2) + MCP tools merged

### Inspect reasoning steps

```bash
curl "http://localhost:3000/api/reasoning?userId=<your-session-id>"
```

### Server log reference

| Log line | Meaning |
|---|---|
| `[nams:tools] MCP connected — tools: ...` | `toolsWithMcp` connected MCP successfully |
| `[nams:tools] query_memory` | Model called query_memory |
| `[nams:tools] store_memory` | Model stored a memory |
| `[chat] tools=N` | N total tools (NAMS + MCP) registered with the agent |
| `[chat] Done \| queries=N stores=N` | Turn complete summary |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_API_KEY` | Yes | — | API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `NAMS_MODE` | No | `provider` | `provider` (transparent) or `tools` (model-driven) |
| `MEMORY_WORKSPACE_ID` | No | _(default)_ | Pin to a specific NAMS workspace |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | LLM model ID |
| `MCP_URL` | No | — | Neo4j MCP server URL (enables live graph access) |
| `MCP_PORT` | No | — | Local MCP server port (`http://localhost:{PORT}/mcp`) |
| `MCP_NEO4J_USERNAME` | No | — | MCP server username (Basic Auth) |
| `MCP_NEO4J_PASSWORD` | No | — | MCP server password (Basic Auth) |

MCP is disabled when `MCP_NEO4J_USERNAME` / `MCP_NEO4J_PASSWORD` are blank.

---

## Dependencies

| Package | Role |
|---------|------|
| `@neo4j-labs/nams-ai-provider` | NAMS integration — `createNams()`, `createNamsProvider()`, `toolsWithMcp()` |
| `@neo4j-labs/agent-memory` | NAMS REST client (peer dependency of nams-ai-provider) |
| `ai` (Vercel AI SDK v6) | `ToolLoopAgent`, `tool`, `createUIMessageStream`, `useChat` |
| `@ai-sdk/openai` | OpenAI model provider |
| `@ai-sdk/react` | `useChat` React hook |
| `@ai-sdk/mcp` | MCP client (peer dependency used by nams-ai-provider) |
| `@neo4j-ndl/react` | Neo4j Design Language UI components |
| `zod` | Input schema validation for memory tools |
| `next` | App framework and API routes |

---

## Troubleshooting

**Memory not persisting across sessions**
- Check that `userId` is stable — the app reads `localStorage.getItem('nams-session-id')` and sends it as `sessionId`
- In tools mode: confirm server logs show `[nams:tools] store_memory — stored OK`
- Verify `MEMORY_API_KEY` is set; restart the dev server after changing `.env.local`

**Model never calls memory tools (tools mode)**
- Confirm `NAMS_MODE=tools` is set and the server restarted
- Try `OPENAI_MODEL=gpt-4o` — `gpt-4o-mini` is occasionally unreliable with multi-tool cycles
- Check server logs: `[chat] tools=N` should show N ≥ 2

**MCP connection fails**
- Verify `MCP_URL`, `MCP_NEO4J_USERNAME`, and `MCP_NEO4J_PASSWORD` are all set
- The route falls back to NAMS tools only when MCP is unavailable — check logs for the warning

**HTTP 503 / `MEMORY_API_KEY` not set**
- Generate a free key at [memory.neo4jlabs.com](https://memory.neo4jlabs.com)
- Restart `npm run dev` after updating `.env.local`

---

## Resources

- [Neo4j Agent Memory Service](https://memory.neo4jlabs.com)
- [Vercel AI SDK — agents and memory](https://sdk.vercel.ai/docs/agents/memory)
- [`@neo4j-labs/nams-ai-provider` source](../nams-provider)
- [`@neo4j-labs/agent-memory` on npm](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Source code — neo4j-agent-integrations](https://github.com/neo4j-labs/neo4j-agent-integrations/tree/main/vercel-agent)
