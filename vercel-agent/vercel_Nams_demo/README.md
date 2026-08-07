# NAMS Chat — Vercel AI SDK + Neo4j Agent Memory System

A production-ready Next.js chat application demonstrating **NAMS (Neo4j Agent Memory System)** integrated with the **Vercel AI SDK**. Serves as both a working example and a reference client for the [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) package — persistent memory backed by Neo4j with zero infrastructure to manage.

**Key features:**
- **Three memory integration modes** — provider middleware, model-instance middleware, or explicit model-driven tools
- **Live database access** — optional Neo4j MCP server integration for real-time graph queries, available in every mode
- **Persistent cross-session memory** — facts, preferences, and interaction history recalled across page reloads
- **Reasoning trace** — per-step tool-call record stored in NAMS and surfaced in the UI
- **Portable** — all NAMS memory logic lives in `@neo4j-labs/nams-ai-provider` (installed from npm); drop it into any Vercel AI SDK project

---

## Quick Start

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/vercel-agent/vercel_Nams_demo

npm install --legacy-peer-deps    # --legacy-peer-deps: NDL components pin React 18

cp .env.local.example .env.local  # set MEMORY_API_KEY and OPENAI_API_KEY at minimum

npm run dev                       # http://localhost:3000
```

`@neo4j-labs/nams-ai-provider` is a normal npm dependency (`^0.1.0` in `package.json` — the only version currently published to npm) — nothing to build or link locally. This package's peer dependencies target **Vercel AI SDK v6** (`ai@~6.0.0`, `@ai-sdk/mcp@~1.0.0`), so this demo pins matching `ai`/`@ai-sdk/*` versions rather than the newer v7 line. A `.npmrc` with `legacy-peer-deps=true` is included to smooth over a minor `zod` peer-range mismatch — plain `npm install` works out of the box.

---

## Integration Modes

All three modes talk to the same NAMS backend through the same package. Pick based on where you want memory to live in your control flow.

```env
NAMS_MODE=provider     # (default) transparent memory, wraps a provider
NAMS_MODE=middleware   # transparent memory, wraps a model instance
NAMS_MODE=tools        # model calls query_memory / store_memory explicitly
```

| Mode | Call | Memory handling | Tool calls visible in UI |  |
|------|------|-----------------|--------------------------|---------|
| **provider** | `createNamsProvider({ baseProvider, scope }).languageModel(id)` | `LanguageModelV4Middleware` injected by the provider | No | |
| **middleware** | `createNams().wrap(model, scope)` | Same middleware, applied to an already-resolved model | No |  |
| **tools** | `createNams().toolsWithMcp(scope, mcpConfig?)` | `query_memory` + `store_memory` tools the model drives | Yes |  |

Choose **provider** when you construct models from a provider and want a drop-in replacement. Choose **middleware** when the base model is already resolved (e.g. it isn't always `openai`). Choose **tools** when you want the memory cycle to be explicit and inspectable.

---

### Mode 1 — Provider (transparent)

`createNamsProvider()` returns a `ProviderV4`-compatible provider. Every `languageModel(id)` call resolves through the base provider and wraps the result with a `LanguageModelV4Middleware`: memories are retrieved and injected into the prompt before the call, and the turn is persisted after it.

```typescript
// app/api/chat/route.ts
import { createNamsProvider } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';

const model = createNamsProvider({
  apiKey:       process.env.MEMORY_API_KEY!,
  workspaceId:  process.env.MEMORY_WORKSPACE_ID,
  baseProvider: openai,
  scope:        { userId, conversationId },
}).languageModel('gpt-5.4-mini');
```

Options worth knowing: `maxMemories` (default 6) caps how many memories are injected per turn, `persistInteractions` (default true) toggles write-back, and `extractionModel` builds a real entity graph per stored turn at the cost of one extra model call.

### Mode 2 — Middleware (transparent)

Identical memory behaviour, applied to a model instance instead of a provider:

```typescript
import { createNams } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';

const nams  = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const model = nams.wrap(openai('gpt-5.4-mini'), { userId, conversationId });
```

### Mode 3 — Tools (model-driven)

`createNams().toolsWithMcp()` returns `{ query_memory, store_memory }` merged with any Neo4j MCP tools in a single object, plus one `close()` covering both connections. The model decides when to call each tool; [`SYSTEM_PROMPT`](lib/constants.ts) enforces the cycle.

```typescript
import { createNams, enforceQueryMemory } from '@neo4j-labs/nams-ai-provider';
import { getNamsMcpConfig } from '@/lib/neo4j-mcp';
import { SYSTEM_PROMPT } from '@/lib/constants';
import { openai } from '@ai-sdk/openai';
import { ToolLoopAgent, stepCountIs } from 'ai';

const { tools, close } = await createNams({ apiKey })
  .toolsWithMcp({ userId, conversationId }, getNamsMcpConfig());

const agent = new ToolLoopAgent({
  model:        openai('gpt-5.4-mini'),
  instructions: SYSTEM_PROMPT,
  tools,
  prepareStep:  enforceQueryMemory({ graceSteps: 2 }),
  stopWhen:     stepCountIs(10),
  onFinish:     async () => { await close(); },
});
```

`enforceQueryMemory({ graceSteps: 2 })` is a `prepareStep` guard: if the model hasn't called `query_memory` within the first two steps, the loop forces it. Without it, smaller models regularly answer from conversation history alone and skip memory entirely. It is applied in tools mode only — the other two modes have no memory tools to enforce.

Calling `toolsWithMcp(scope)` with no second argument returns NAMS memory tools only, and `close()` is a no-op.

**MCP in provider / middleware mode:** `toolsWithMcp()` also emits `query_memory`/`store_memory`, which would double-handle memory alongside the middleware. So those modes call [`getNeo4jMcpTools()`](lib/neo4j-mcp.ts) directly and pass only the MCP tools to the agent.

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
│  │  recent / observ. /  │  │  step 1 → step 2 → … → step N    │   │
│  │  reasoning tabs      │  │  reasoning / action / result     │   │
│  └──────────────────────┘  └──────────────────────────────────┘   │
└───────────────────────┬───────────────────────────────────────────┘
                        │  HTTP streaming (UI message stream)
                        ▼
┌────────────────────────────────────────────────────────────────────┐
│  Next.js API Routes (Node.js runtime)                              │
│                                                                    │
│  POST /api/chat                      GET /api/reasoning            │
│  ───────────────────────────────     ─────────────────────────     │
│  1. Parse UIMessages + sessionId     1. findExistingConversation   │
│  2. Resolve model by NAMS_MODE       2. client.reasoning.listSteps │
│  3. Connect MCP (mode-dependent)     3. Return step array as JSON  │
│  4. Build DATABASE ACCESS prompt        (no conversation → [])     │
│  5. ToolLoopAgent streams response                                 │
│  6. onFinish → recordStep → close()                                │
│                                                                    │
└───────────────────────┬────────────────────────────────────────────┘
                        │  HTTPS REST
                        ▼
┌────────────────────────────────────────────────────────────────────┐
│  NAMS  —  https://memory.neo4jlabs.com                             │
│  (@neo4j-labs/agent-memory SDK, backed by Neo4j AuraDB)            │
│                                                                    │
│  ┌──────────────────┐  ┌───────────────────┐  ┌────────────────┐   │
│  │  Short-Term      │  │  Long-Term        │  │  Reasoning     │   │
│  │  (conversation)  │  │  (graph entities) │  │  (step records)│   │
│  │  • search        │  │  • facts          │  │  • reasoning   │   │
│  │  • per convId    │  │  • user_pref      │  │  • actionTaken │   │
│  │  • cross-session │  │  • patterns       │  │  • result      │   │
│  └──────────────────┘  └───────────────────┘  └────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### Memory flow per turn (tools mode)

```
User sends message
      │
      ▼
[tool] query_memory ──────────────────────────────────────────────┐
      │  searches:                                                 │
      │  • current conversation  (short-term)                      │
      │  • past conversations    (cross-session, same userId)      │
      │  • long-term graph       (entities, facts, preferences)    │
      │  • prior reasoning steps                                   │
      │◄── returns ranked MemoryHit[] ─────────────────────────────┘
      │      (forced by enforceQueryMemory if skipped for 2 steps)
      │
[tool] MCP database tools (if configured)
      │  schema lookup → Cypher read → results
      │
      ▼
LLM composes personalised answer
      │
      ▼
[tool] store_memory
      │  routes by type:
      │  interaction      → short-term conversation thread
      │  fact             → long-term graph entity
      │  user_preference  → long-term graph entity
      │  pattern          → long-term graph entity
      ▼
onFinish → recordStep (one per agent step) → close()
      │
      ▼
Response streams to browser
```

In provider and middleware modes the two `[tool]` memory steps disappear — retrieval and persistence happen inside the model wrapper — and the agent runs a single step unless MCP tools are attached.

---

## Project Structure

```
vercel_Nams_demo/
│
├── app/
│   ├── api/
│   │   ├── chat/route.ts          ← POST /api/chat — mode switching, ToolLoopAgent
│   │   └── reasoning/route.ts     ← GET  /api/reasoning — fetch stored reasoning steps
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx                   ← dark/light shell + AppHeader + ChatComponent
│
├── components/
│   ├── AppHeader.tsx
│   └── chat/
│       ├── ChatComponent.tsx      ← useChat, streaming, session id, reasoning fetch
│       ├── MemoryPanel.tsx        ← retrieved memories (recent / observations / reasoning)
│       ├── ReasoningPanel.tsx     ← per-step reasoning trace
│       └── styles.ts
│
├── lib/
│   ├── constants.ts               ← SYSTEM_PROMPT + buildDbToolsPrompt()
│   └── neo4j-mcp.ts               ← MCP client, auth resolution, explainMcpError()
│
├── test/
│   ├── chat-route.test.ts         ← mode wiring + error paths for /api/chat
│   └── reasoning-route.test.ts    ← trace lookup + error paths for /api/reasoning
│
├── types/index.ts                 ← MemoryHit, QueryOutput, ReasoningStep, ParsedMemory
├── utils/message.ts               ← getMsgText, parseMemory, formatErrorMessage
├── constants.ts                   ← DEFAULT_SUGGESTIONS, SESSION_STORAGE_KEY
├── .env.local.example
├── package.json
├── vitest.config.ts
└── next.config.js
```

**NAMS integration lives entirely in `@neo4j-labs/nams-ai-provider`** — a published npm package, not vendored source. The demo only wires it up.

---

## Setup

### 1. Install

```bash
npm install --legacy-peer-deps
```

`--legacy-peer-deps` is required: `@neo4j-ndl/react` pins React 18 while some AI SDK packages advertise React 19.

### 2. Configure

```bash
cp .env.local.example .env.local
```

Minimum viable config:

```env
MEMORY_API_KEY=nams_...        # free key from https://memory.neo4jlabs.com
OPENAI_API_KEY=sk-proj-...
NAMS_MODE=tools                # start here — the memory cycle is visible in the UI
```

### 3. Run

```bash
npm run dev
# http://localhost:3000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_API_KEY` | Yes | — | API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com). Missing → every `/api/chat` request returns **503** |
| `OPENAI_API_KEY` | Yes | — | OpenAI API key, read by `@ai-sdk/openai` |
| `NAMS_MODE` | No | `provider` | `provider`, `middleware`, or `tools` |
| `MEMORY_WORKSPACE_ID` | No | _(key default)_ | Pin to a specific NAMS workspace |
| `OPENAI_MODEL` | No | `gpt-5.4-mini` | LLM model ID |
| `NAMS_EXTRACTION_MODEL` | No | _(off)_ | When set, builds a real entity graph per stored memory (one extra model call). Applies in all three modes |
| `MCP_URL` | No | — | Neo4j MCP server URL (enables live graph access) |
| `MCP_PORT` | No | — | Used as `http://localhost:{PORT}/mcp` when `MCP_URL` is unset |
| `MCP_BEARER_TOKEN` | No | — | `Authorization: Bearer` — takes precedence over Basic |
| `MCP_NEO4J_USERNAME` | No | — | Basic auth username |
| `MCP_NEO4J_PASSWORD` | No | — | Basic auth password |

MCP stays disabled unless `MCP_URL` (or `MCP_PORT`) is set **and** one auth pair is supplied: either `MCP_BEARER_TOKEN`, or both `MCP_NEO4J_USERNAME` and `MCP_NEO4J_PASSWORD`.

Not sure which your server wants? `curl -i -X POST $MCP_URL` and read the `WWW-Authenticate` header: `Bearer …` means a token, `Basic …` means user/password.

---

## Testing the Integration Paths

The demo is the reference client for the provider, so each supported wiring has a manual path worth walking after an upgrade.

**Path A — tools mode, no MCP** (`NAMS_MODE=tools`, MCP vars unset)

Exercises `createNams().toolsWithMcp(scope)` — memory tools only.

```
Send: "My name is Alex and I like TypeScript"
→ Memory + Reasoning panels appear above the answer
→ Reasoning trace: query_memory → answer → store_memory
→ Send: "What language do I like?"
→ query_memory returns found=true; the model answers from memory
```

**Path B — tools mode + MCP** (add `MCP_URL` plus `MCP_BEARER_TOKEN` *or* `MCP_NEO4J_USERNAME`/`MCP_NEO4J_PASSWORD`)

Exercises `createNams().toolsWithMcp(scope, mcpConfig)` — memory + database tools merged.

```
Send: "What nodes are in my Neo4j database?"
→ [chat] model=gpt-5.4-mini  maxSteps=10  tools=5  db=[get_neo4j_schema, read_neo4j_cypher, write_neo4j_cypher]
→ Agent calls the schema tool, then the read tool, then offers to store findings
```

Exact tool names vary by server. `buildDbToolsPrompt()` builds the DATABASE ACCESS block from whatever the server reported at connect time, so the prompt never advertises a tool the model can't call.

**Path C — provider mode** (`NAMS_MODE=provider`)

Exercises `createNamsProvider()` — transparent middleware, no visible tool calls.

```
Send: "My favourite colour is blue"
→ No query_memory / store_memory in the logs — memory is middleware-driven
→ Refresh the page (same localStorage session id); send: "What's my favourite colour?"
→ Model answers "blue" — retrieved before the model call
```

**Path D — middleware mode** (`NAMS_MODE=middleware`)

Same observable behaviour as Path C, via `createNams().wrap()` instead of a provider.

### Inspect reasoning steps directly

```bash
curl "http://localhost:3000/api/reasoning?userId=<your-session-id>"
```

The session id is in `localStorage` under `nams-session-id`.

### Server log reference

Every request opens with a banner and closes with a summary:

| Log line | Meaning |
|---|---|
| `[chat] POST /api/chat  mode=… mcp=…` | Mode resolved; whether MCP env vars are complete |
| `[chat]   userId=… conv=… query="…"` | Scope and truncated user message for this turn |
| `[neo4j-mcp] Connected — tools: …` | MCP connected; the names it reported |
| `[chat]   model=… maxSteps=… tools=N  db=[…]` | Tool count registered with the agent; `db=[…]` only when database tools attached |
| `[chat]   Neo4j MCP is configured but NOT connected` | Env vars set but the connection failed — database questions will fail |
| `[chat] Done \| steps=N queries=N stores=N elapsed=Xms` | Turn summary (`queries`/`stores` are 0 outside tools mode) |
| `[chat]   tokens in=… out=…` | Usage for the turn |
| `[chat] Empty answer (finishReason=…)` | Agent produced no text; fallback message emitted to the UI |
| `[reasoning/GET] Returning N steps` | Reasoning trace served to the panel |
| `[nams] …` | Non-fatal warning from the provider package itself |

### Automated tests

`test/` unit-tests both API routes against a **mocked** `@neo4j-labs/nams-ai-provider` — no live NAMS or OpenAI credentials needed.

```bash
npm test          # single run — 18 tests
npm run test:watch
```

| File | Covers |
|---|---|
| `test/chat-route.test.ts` | provider mode wraps via `createNamsProvider(...).languageModel()`; middleware mode wraps via `createNams().wrap()`; tools mode leaves the base model unwrapped and sources tools from `toolsWithMcp()`; MCP failure falls back to NAMS-only tools; DATABASE ACCESS prompt built from returned tool names only; `enforceQueryMemory` applied in tools mode only; fallback text on an empty answer; `onFinish` persists the trace via `makeClient()`/`resolveConversation()`; 400/503 paths |
| `test/reasoning-route.test.ts` | `makeClient()`/`findExistingConversation()` called with the right config; no conversation yet returns `{ steps: [] }` rather than an error; 400/503/500 paths |

Run these after any provider upgrade to confirm the demo still speaks the package's current API before clicking through the UI.

---

## Using NAMS in Your Own Project

```bash
npm install @neo4j-labs/nams-ai-provider @neo4j-labs/agent-memory ai zod
```

```typescript
import { createNamsProvider, createNams } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';

// Provider mode — transparent
const model = createNamsProvider({ apiKey, baseProvider: openai, scope: { userId } })
  .languageModel('gpt-5.4-mini');

// Middleware mode — transparent, wraps an existing model
const wrapped = createNams({ apiKey }).wrap(openai('gpt-5.4-mini'), { userId });

// Tools mode — model-driven, tool calls visible in the UI
const { tools, close } = await createNams({ apiKey }).toolsWithMcp({ userId });
```

---

## Troubleshooting

**Memory not persisting across sessions**
- Check that the session id is stable — the app reads `localStorage.getItem('nams-session-id')` and sends it as `sessionId`; clearing site data starts a new user
- Verify `MEMORY_API_KEY` is set and restart the dev server after editing `.env.local`
- In tools mode, confirm the reasoning trace shows a `store_memory` step

**Model never calls memory tools (tools mode)**
- Confirm `NAMS_MODE=tools` and that the server restarted
- `enforceQueryMemory` forces `query_memory` after 2 steps, so a total absence usually means the tools weren't attached — check `[chat] … tools=N` shows N ≥ 2
- Try a larger model, e.g. `OPENAI_MODEL=gpt-5.4` — smaller models are less reliable with multi-tool cycles

**MCP connection fails**
- Verify a URL and one complete auth pair are set (see the env table)
- **HTTP 401** is usually the wrong auth *scheme*, not wrong credentials. `explainMcpError()` re-probes the endpoint on a 401 and logs the server's `WWW-Authenticate` challenge, e.g. `server requires bearer auth, but the MCP_* env vars produced basic`. Hosted Aura / NeoCompanion endpoints are OAuth 2.1 — mint a token and set `MCP_BEARER_TOKEN`
- Tools mode falls back to NAMS-only tools when MCP is unavailable; provider/middleware modes continue with no tools at all

**Model answers from memory instead of querying the database**
- Check for `db=[…]` in the `[chat] model=…` line. No `db=[…]` means no database tools were attached, so the model *cannot* query — fix the connection first
- The DATABASE ACCESS prompt block is generated from the tool names the server reports at connect time, so it always matches what the model can actually call

**"I ran out of steps…" in the chat**
- The tool loop hit `maxSteps=10` without producing text. Usually a model looping on `query_memory` with reworded keywords — try a larger model, or check whether the question actually needs database tools that aren't connected

**HTTP 503 / `MEMORY_API_KEY is not set`**
- Generate a free key at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) and restart `npm run dev`

**`400 string_above_max_length` from OpenAI, or a vague "I was not able to produce an answer"**
- A `read-cypher` call without a `LIMIT` clause can return a very large result set, exceeding OpenAI's per-request size limit and failing the whole turn. `lib/neo4j-mcp.ts`'s `capToolOutputs()` truncates any tool result over 50,000 characters and nudges the model to add a `LIMIT` clause — if you still hit this, ask a narrower question or add `LIMIT 25` yourself

### Known limitation (upstream package)

During end-to-end testing with two different `userId`s sharing one NAMS workspace, a brand-new user's very first turn occasionally surfaced a fact stored under a *different* user minutes earlier. `route.ts` passes a correctly-scoped `{ userId, conversationId }` to both `createNamsProvider(...)` and `createNams(...).wrap(...)`, so this behavior appears to originate inside `@neo4j-labs/nams-ai-provider`/`@neo4j-labs/agent-memory`'s conversation/entity retrieval rather than in this demo's code. If you see unexpected cross-user recall, pass an explicit `conversationId` per user/session and report the observation upstream at [neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory).

---

## Dependencies

| Package | Role |
|---------|------|
| `@neo4j-labs/nams-ai-provider` | NAMS integration — `createNams()`, `createNamsProvider()`, `enforceQueryMemory()` |
| `@neo4j-labs/agent-memory` | NAMS REST client used by the provider |
| `ai` (Vercel AI SDK v6) | `ToolLoopAgent`, `createUIMessageStream`, `result.toUIMessageStream()`, `DefaultChatTransport` |
| `@ai-sdk/openai` | OpenAI model provider |
| `@ai-sdk/react` | `useChat` React hook |
| `@ai-sdk/mcp` | MCP client used by `lib/neo4j-mcp.ts` |
| `@neo4j-ndl/react`, `@neo4j-ndl/base` | Neo4j Design Language UI components |
| `zod` | Tool input schemas |
| `next`, `react`, `react-dom` | App framework and UI runtime |
| `vitest` (dev) | Route-level tests (`npm test`) |

---

## Resources

- [Neo4j Agent Memory Service](https://memory.neo4jlabs.com)
- [`@neo4j-labs/nams-ai-provider` on npm](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) — [source](https://github.com/neo4j-labs/agent-memory/tree/main/typescript/packages/vercel-ai-provider)
- [`@neo4j-labs/agent-memory` on npm](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Vercel AI SDK docs](https://ai-sdk.dev/docs)
- [Source code — neo4j-agent-integrations](https://github.com/neo4j-labs/neo4j-agent-integrations/tree/main/vercel-agent)
