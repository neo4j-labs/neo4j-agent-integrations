# Vercel AI SDK + Neo4j

Neo4j as an agent's knowledge layer **and** its memory, on the
[Vercel AI SDK](https://ai-sdk.dev).

Two ways in:

| | Start here if |
|---|---|
| **[`notebook/`](notebook/)** | You want to read one file and understand the wiring. Five runnable Node scripts, plain JS, no build step. |
| **[`vercel_Nams_demo/`](vercel_Nams_demo/)** | You want a production shape. Next.js chat app with memory and reasoning rendered on screen; the reference client for the memory package. |

Building on **eve**, Vercel's durable agent framework, instead of the SDK
directly? See **[`../vercel-eve/`](../vercel-eve/)** — same memory package, and a
[tutorial that deploys to Vercel](../vercel-eve/TUTORIAL.md).

---

## Two integrations, not one

Most platform integrations in this repo connect an agent to a Neo4j graph it can
query. This one does that *and* uses Neo4j for what the agent remembers.

**1. Graph access — [MCP](https://github.com/neo4j/mcp)**

```typescript
import { createMCPClient } from '@ai-sdk/mcp';

const client = await createMCPClient({ transport: { type: 'http', url: MCP_URL, headers } });
const tools = await client.tools();   // get_neo4j_schema, read_neo4j_cypher, …
```

**2. Memory — [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider)**

```typescript
import { createNams } from '@neo4j-labs/nams-ai-provider';

// Memory becomes a property of the model: retrieved before each call,
// persisted after. The agent loop does not change.
const model = createNams({ apiKey }).wrap(openai('gpt-5.4-mini'), { userId });
```

A context window is a working set, not a memory. The distinction that matters is
whether anything survives the session ending — which is why every example here
is checked by starting a *new* session and asking the agent what it knows.

---

## Memory integration modes

One package, three ways to attach it (`@neo4j-labs/nams-ai-provider@0.2.0`).
All talk to the same [NAMS](https://memory.neo4jlabs.com) backend.

| Mode | Call | Memory handling | Tool calls visible |
|------|------|-----------------|--------------------|
| **provider** | `createNamsProvider({ baseProvider, scope }).languageModel(id)` | Middleware injected by the provider | No |
| **middleware** | `createNams().wrap(model, scope)` | Same middleware, on a resolved model | No |
| **tools** | `createNams().toolsWithMcp(scope, mcpConfig)` | `query_memory` / `store_memory` the model drives | Yes |

Choose **provider** when you build models from a provider and want a drop-in
replacement; **middleware** when the base model is already resolved (it isn't
always `openai`); **tools** when the memory cycle should be inspectable.

In tools mode, pair the tools with `enforceQueryMemory({ graceSteps: 2 })` as
`prepareStep`. Without it, smaller models regularly answer from conversation
history and never consult memory at all.

`NAMS_MODE` selects between them in both `notebook/4-nams-provider-agent.mjs`
and the Next.js demo, so you can compare them against the same conversation.

---

## Quick start

```bash
# Scripts — fastest path to a working agent
cd notebook
cp .env.example .env          # MEMORY_API_KEY + OPENAI_API_KEY at minimum
npm install
node 3-memory-agent.mjs

# Next.js app
cd ../vercel_Nams_demo
npm install --legacy-peer-deps
cp .env.local.example .env.local
npm run dev                   # http://localhost:3000
```

`--legacy-peer-deps` is required in the demo: `@neo4j-ndl/react` pins React 18
while some AI SDK packages advertise React 19. Plain `npm install` fails and can
leave `node_modules` half-pruned.

Free NAMS keys: [memory.neo4jlabs.com](https://memory.neo4jlabs.com).

---

## Credentials

| Variable | Needed for | Notes |
|---|---|---|
| `MEMORY_API_KEY` | all memory examples | `nams_...`; missing → `/api/chat` returns 503 |
| `MEMORY_WORKSPACE_ID` | multi-tenant setups | Blank uses the key's workspace. See the isolation note below |
| `OPENAI_API_KEY` | the model | Or the key matching `AI_PROVIDER` — the notebook also speaks Google, Anthropic, and Mistral |
| `MCP_URL` / `MCP_PORT` | live graph access | Without one, memory examples still run; graph tools are simply absent |
| `MCP_BEARER_TOKEN` | OAuth MCP servers | Takes precedence over Basic |
| `MCP_NEO4J_USERNAME` / `_PASSWORD` | Basic-auth MCP servers | Falls back to `NEO4J_USERNAME` / `NEO4J_PASSWORD` |

**HTTP 401 from an MCP server is usually the wrong auth *scheme*, not wrong
credentials.** `curl -i -X POST $MCP_URL` and read `WWW-Authenticate`: `Bearer`
means a token, `Basic` means user/password. Hosted Aura and NeoCompanion
endpoints are OAuth 2.1, so mint a token and set `MCP_BEARER_TOKEN` — Basic auth
is always rejected there.

---

## Known limitations

Behaviour of the hosted NAMS service, not of these examples.

1. **Retrieval is lexical, not semantic.** Search matches keywords with AND
   semantics and returns no scores, so a paraphrased query misses a memory that
   is definitely stored. The provider fans queries out into single keywords to
   compensate. Prefer modes where the *user's* words form the query over modes
   where the model paraphrases.
2. **Long-term entities are workspace-scoped, not user-scoped.** `userId`
   correctly scopes conversations, but stored facts carry no user id, so two
   users sharing a workspace can surface each other's facts. **For hard tenant
   isolation, use one workspace per tenant** via `MEMORY_WORKSPACE_ID`.
3. **Entity extraction is asynchronous.** A fact stored this turn is not
   immediately searchable in the long-term graph; short-term conversation memory
   is available right away.
4. **`deleteMessage` is unsupported on the hosted API** — only whole-conversation
   delete works.

Tracking upstream at
[neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory).

---

## Where the code lives

The memory logic is **not vendored here**. `@neo4j-labs/nams-ai-provider` is a
published npm package; these directories only wire it up. Package source lives in
[neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory/tree/main/typescript/packages/vercel-ai-provider).

```
vercel-agent/
├── notebook/            # 0-direct-query → 4-nams-provider-agent, plus shared mcp/prompts/providers
└── vercel_Nams_demo/    # Next.js app: chat, memory panel, reasoning trace, route tests
```

---

## Resources

- [Vercel AI SDK docs](https://ai-sdk.dev/docs) · [Agent memory providers](https://ai-sdk.dev/docs/agents/memory)
- [NAMS](https://memory.neo4jlabs.com) · [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) · [`@neo4j-labs/agent-memory`](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Neo4j MCP server](https://github.com/neo4j/mcp)
- [`../vercel-eve/`](../vercel-eve/) — the same memory layer on Vercel's eve framework
- Demo database: `neo4j+s://demo.neo4jlabs.com:7687` (companies/companies)
