# Vercel eve + Neo4j

Persistent, graph-backed memory for [eve](https://vercel.com/docs/eve), Vercel's
open-source framework for durable backend agents.

**[→ Tutorial: build and deploy an eve agent on Vercel with Neo4j memory](TUTORIAL.md)**
**[→ Working project: `industry-research-agent/`](industry-research-agent/)**
**[→ Demo script and the pitch to Vercel](PITCH_AND_DEMO.md)**

---

## Overview

**eve** is a filesystem-first framework for durable backend AI agents. You
author an agent as files under `agent/` — instructions, tools, skills,
connections, channels, hooks, schedules — and eve compiles them into a service
with durable sessions, a reconnectable stream, sandboxed compute, approvals,
tracing, and evals. It runs locally, on Vercel, or on any Node host.

**Key features**
- Durable execution: sessions survive crashes, redeploys, and days-long gaps
- Filesystem registration — a file's path is its name and its capability
- Deploys to Vercel Workflow, Cron, and Sandbox with one command
- Model-agnostic through AI Gateway or any AI SDK provider
- Built-in evals that drive the real HTTP surface

**Official resources**
- Framework: https://vercel.com/eve · Docs: https://vercel.com/docs/eve
- Source: https://github.com/vercel/eve (Apache-2.0)
- Docs are bundled in the installed package at `node_modules/eve/docs/`

**Prior art.** William Lyon's
[Give Your Vercel Eve Agent a Memory](https://lyonwj.com/blog/agent-memory-with-eve-and-nams)
builds the same combination against a National Parks trip planner
([TrailGraph](https://github.com/johnymontana/trailgraph)). It is the better
read for *why* graph memory changes an application; this page is the
integration reference — every eve attachment point, the API constraints that
break silently, and what is missing. The two differ in one substantive way,
which [Co-locating memory and domain data](#co-locating-memory-and-domain-data)
covers.

**Status:** eve is in beta; APIs may change before GA. Verified here against
`eve@0.31.3`, `ai@7.0.58`, `@neo4j-labs/nams-ai-provider@0.2.0`.

---

## Why memory is the gap

eve is explicit that durable *session* state is not memory. From its own docs
on `defineState`:

> `defineState` holds conversation-scoped working memory that lives and dies
> with the session. […] Anything that has to outlive the session, be shared
> across sessions or users, or be queried independently of a turn belongs in an
> external store.

The framework points at an integration gallery for that store. As of this
writing the registry lists three memory options — `connection/mem0`,
`extension/upstash-agentkit`, and `extension/arcana` — all key/value or vector
stores. **None of them is a graph.**

That matters for agent memory specifically. What an agent needs to recall is
mostly relational: this user follows these sectors, which contain these
companies, which compete with these others, which were mentioned in these
articles. Retrieval over a flat store returns the facts it matched; retrieval
over a graph can also return what those facts are connected to, and can explain
*why* something was recalled by naming the path. NAMS stores memory as nodes and
edges in Neo4j, so the memory and the domain knowledge are queryable together.

---

## Extension points

eve exposes four places memory can attach. Three are used here.

### 1. The model (`agent/agent.ts`)

`defineAgent({ model })` accepts a resolved AI SDK `LanguageModel`, and
`defineDynamic` can resolve one per step. Since
`@neo4j-labs/nams-ai-provider` produces a memory-wrapped `LanguageModelV4`,
memory becomes a property of the model — invisible to the harness, tools, and
channels.

```ts title="agent/agent.ts"
import { defineAgent, defineDynamic } from "eve";
import { createNams } from "@neo4j-labs/nams-ai-provider";
import { gateway } from "ai";

const nams = () => createNams({ apiKey: process.env.NAMS_API_KEY! });

export default defineAgent({
  model: defineDynamic({
    fallback: "openai/gpt-5.4",
    events: {
      "step.started": (_event, ctx) =>
        nams().wrap(gateway("openai/gpt-5.4"), { userId: userIdFrom(ctx) }),
    },
  }),
});
```

Constraints worth knowing: only `step.started` may return a live model object
(session- and turn-scoped selections are serialized, so they must be id
strings), and `fallback` must stay a plain id because it anchors build-time
routing and context-window metadata.

### 2. Instructions and hooks (`agent/instructions/`, `agent/hooks/`)

The split a packaged memory extension would ship, and the shape eve's own
[multi-tenant memory pattern](https://vercel.com/docs/eve/patterns/multi-tenant-memory)
recommends:

- **Recall** — `defineDynamic` in `agent/instructions/` resolving on
  `turn.started`, returning `defineInstructions({ markdown })`. Runs before the
  prompt is assembled; resolving per turn (not per session) means a fact stored
  on turn 1 is in context by turn 2.
- **Retention** — `defineHook` in `agent/hooks/` on `message.received` /
  `message.completed` / `turn.completed`. Fires after eve durably records each
  event, so storage never depends on the model choosing to call a tool.

Hooks are observe-only and **a thrown hook fails the turn** — always wrap the
store call in `try`/`catch`.

### 3. Tools (`agent/tools/`)

`defineTool` files, or a `defineDynamic` map, expose `recall_memory` and
`remember` to the model. The only mode where memory is visible in the TUI and
in traces, and the only one that supports "forget that."

With dynamic tools, `execute` **must be an inline function expression** — eve
reconstructs it from its closure on replay and does not detect
`execute: namedFn`, which silently breaks after a resume.

### 4. Connections (`agent/connections/`) — for the graph, not the memory

`defineMcpClientConnection` points eve at any Streamable-HTTP or SSE MCP server,
exposing its tools as `<connection>__<tool>`:

```ts title="agent/connections/neo4j.ts"
import { defineMcpClientConnection } from "eve/connections";

export default defineMcpClientConnection({
  url: process.env.MCP_URL!,
  description: "Company News knowledge graph: organizations, people, news.",
  auth: { getToken: async () => ({ token: process.env.MCP_BEARER_TOKEN! }) },
  tools: { allow: ["get_neo4j_schema", "read_neo4j_cypher"] },
});
```

Use this with the [Neo4j MCP server](https://github.com/neo4j/mcp) when you want
schema-driven Cypher. The example project uses typed `defineTool` files against
the driver instead — narrower surface, no server to run, and the model picks an
edge rather than writing Cypher.

---

## Authentication

### Route auth is the memory boundary

In eve the inbound auth walk on `agent/channels/eve.ts` produces
`ctx.session.auth`, and for a memory agent **that principal is the memory
scope**. A tool that accepts a `userId` argument lets a prompt-injected document
address another user's memory; deriving it from `auth.current` does not.

| Mechanism | Support | Notes |
|---|---|---|
| API keys / bearer | ✅ | `httpBasic()`, `jwtHmac()`, `jwtEcdsa()`, or a custom `AuthFn` |
| OIDC (any issuer) | ✅ | `oidc({ issuer, audiences, discoveryUrl })` |
| Vercel OIDC | ✅ | `vercelOidc()`; zero-config for Vercel-to-Vercel callers |
| OAuth 2.1 (outbound) | ✅ | `connect()` from `@vercel/connect/eve`, per-user or app-scoped |
| Anonymous | ⚠️ | `none()` only; fails closed in production otherwise |

The walk is ordered and each entry may accept, skip (`null`), or throw a
specific status. Put your app's authenticator first:

```ts
export default eveChannel({ auth: [appSession(), vercelOidc(), localDev()] });
```

`principalId` must be **stable for the same person forever** — it is the NAMS
user id, so rotating it orphans that user's memory.

`eve init` scaffolds `placeholderAuth()`, which 401s in production. For a memory
agent, shipping it means every caller either fails or collapses into one shared
memory.

### NAMS

A single `nams_...` API key, sent as a bearer token, optionally bound to a
workspace via `NAMS_WORKSPACE_ID`. Free keys at
[memory.neo4jlabs.com](https://memory.neo4jlabs.com).

---

## Industry Research Agent

The repo's [reference agent](../EXAMPLE_AGENT.md), implemented on eve in
[`industry-research-agent/`](industry-research-agent/).

### Scenario

An analyst asks about companies, competitive position, and news. The agent
traverses the Company News knowledge graph — 250k Diffbot entities — and
remembers each analyst's beat, tracked companies, and reporting preferences
across sessions and deployments.

### Architecture

```
   Analyst
      │  POST /eve/v1/session          GET /eve/v1/session/:id/stream
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  eve runtime (local, Vercel, or any Node host)                  │
│                                                                 │
│  agent/channels/eve.ts   auth walk → ctx.session.auth           │
│           │                                                     │
│           ▼              ┌── memory (exactly one mode) ──────┐  │
│  agent/agent.ts ─────────┤ wrap   dynamic model, step.started│  │
│    dynamic model         │ hooks  instructions/ + hooks/     │  │
│           │              │ tools  dynamic tools/             │  │
│           │              └───────────────┬───────────────────┘  │
│           ▼                              │                      │
│  harness ── tool loop                    │                      │
│    company_profile · company_network · search_news              │
└───────────┬──────────────────────────────┼──────────────────────┘
            │ bolt (read-only)             │ HTTPS
            ▼                              ▼
   ┌──────────────────────┐   ┌──────────────────────────────────┐
   │ Company News graph   │   │ NAMS — memory.neo4jlabs.com      │
   │ demo.neo4jlabs.com   │   │  short-term  conversation thread  │
   │ 250k orgs, people,   │   │  long-term   entities + relations │
   │ articles, embeddings │   │  reasoning   step records         │
   └──────────────────────┘   └──────────────┬───────────────────┘
                                             │
                                    Neo4j AuraDB
```

### Project layout

```
industry-research-agent/
├── agent/
│   ├── agent.ts                    ← dynamic model; wraps with NAMS in `wrap` mode
│   ├── instructions.md             ← research + memory system prompt
│   ├── channels/eve.ts             ← auth walk = memory boundary
│   ├── instructions/memory.ts      ← `hooks` mode: recall on turn.started
│   ├── hooks/persist-turn.ts       ← `hooks` mode: retention on turn.completed
│   ├── hooks/persist-reasoning.ts  ← all modes: reasoning steps + tool provenance
│   ├── tools/
│   │   ├── company_profile.ts      ← org, HQ, categories, CEO, board
│   │   ├── company_network.ts      ← competitors/suppliers/subsidiaries/investors
│   │   ├── search_news.ts          ← full-text over article chunks
│   │   └── memory.ts               ← `tools` mode: recall_memory + remember
│   └── lib/
│       ├── nams.ts                 ← NAMS config and helpers
│       ├── scope.ts                ← memory identity from verified session auth
│       ├── model.ts                ← AI Gateway or direct provider
│       └── neo4j.ts                ← read-only driver
└── evals/
    ├── graph/company-lookup.eval.ts
    └── memory/cross-session-recall.eval.ts
```

### Dataset

```env
NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687
NEO4J_USERNAME=companies
NEO4J_PASSWORD=companies
NEO4J_DATABASE=companies
```

Verified schema (`CALL db.schema.visualization()` on the live instance):

```
(Organization)-[:IN_CITY]->(City)-[:IN_COUNTRY]->(Country)
(Organization)-[:HAS_CATEGORY]->(IndustryCategory)
(Organization)-[:HAS_CEO|HAS_BOARD_MEMBER]->(Person)
(Organization)-[:HAS_COMPETITOR|HAS_SUPPLIER|HAS_SUBSIDIARY|HAS_INVESTOR]->(Organization)
(Article)-[:MENTIONS]->(Organization)
(Article)-[:HAS_CHUNK]->(Chunk)
```

Indexes: `entity` (full-text, Person/Organization.name), `news_fulltext`
(full-text, Chunk.text), `news` (vector, 1536d, Chunk.embedding).

**The `news` vector index was built with OpenAI `text-embedding-ada-002`.**
Querying it with a different embedding model returns confident nonsense — a
"graph database funding" query against `text-embedding-3-small` returns articles
about hate speech moderation and copper fatigue at ~0.54 cosine, while ada-002
returns the ArangoDB funding coverage at ~0.92. The shipped `search_news` tool
uses the full-text index instead, so it works whichever model the agent routes
to. For the vector variant:

```ts
const { embedding } = await embed({ model: openai.embedding("text-embedding-ada-002"), value: query });
await readQuery(
  `CALL db.index.vector.queryNodes('news', $k, $embedding) YIELD node, score
   MATCH (a:Article)-[:HAS_CHUNK]->(node)
   RETURN a.title AS title, toString(a.date) AS date, node.text AS passage, score
   ORDER BY score DESC`,
  { k: 5, embedding },
);
```

### Memory modes

Set `NAMS_MODE`. Exactly one is active, so no turn is ever stored twice.

| `NAMS_MODE` | eve primitive | Retrieval query written by | Storage driven by | Visible in TUI |
|---|---|---|---|---|
| `wrap` (default) | dynamic model, `step.started` | the user | the model wrapper | no |
| `hooks` | dynamic instructions + hook | the user | the runtime | no |
| `tools` | dynamic tools, `session.started` | the model | the model | yes |

**Reasoning memory is orthogonal to all three.** NAMS's third memory type
records *why* the agent answered as it did — one step per reasoning block, with
the tool calls that step invoked hanging off it. No mode writes it, so
[`hooks/persist-reasoning.ts`](industry-research-agent/agent/hooks/persist-reasoning.ts)
runs in every mode without ever double-storing a turn. It buffers
`actions.requested` / `action.result` / `reasoning.completed` and flushes once
on `turn.completed` — a step's tool calls are only known after its reasoning
block completes, and `recordToolCall` needs the id of the step it belongs to.
Set `NAMS_REASONING=off` to disable; it costs one extra round trip per turn.

This is what `retrieveMemories`' fourth source reads, and what makes "why did
you recommend that?" answerable from recorded provenance. It uses
`findExistingConversation`, never `resolveConversation`: a trace is provenance
for a conversation that already happened and must never be the thing that
creates one.

```ts
// wrap    — transparent, one line
nams().wrap(baseModel(), memoryScope(ctx))

// hooks   — recall
defineInstructions({ markdown: renderMemories(await recall(memoryScope(ctx), event.data.message)) })
// hooks   — retention
await remember(memoryScope(ctx), { content, type: "interaction" })

// tools   — model-driven
recall_memory({ query }) / remember({ content, type })
```

### Verify

```bash
cd industry-research-agent
npm install
cp .env.example .env.local          # add NAMS_API_KEY
npx eve info                        # 3 tools, 0 diagnostics
npx eve eval                        # 2 passed, 6 gates
npm run dev
```

The eval that matters is `memory/cross-session-recall`: it stores a fact, calls
`t.newSession()` to discard the transcript, and asserts the agent still knows
it. That is the assertion that distinguishes memory from a long context window.

---

## Co-locating memory and domain data

Everything above keeps memory and domain knowledge in **two** databases: NAMS
writes to its own Aura instance behind `memory.neo4jlabs.com`, and the tools
read the public `companies` graph over bolt. That is the honest default for a
hosted key, and it is enough for recall — but it is not the thing that makes
graph memory different from a key/value store.

The difference appears when memory and domain data are **nodes in the same
database**, joined by edges. Point NAMS at a Neo4j you control (`endpoint` on
`MemoryClient`, or `NAMS_ENDPOINT` here), load your domain graph into it, and
write a **bridge edge** from the memory graph's `User` to the real entity every
time you store a preference:

```cypher
// The analyst says "I track Neo4j" → canonicalize to the Organization node.
MATCH (u:User {userId: $userId})
MATCH (o:Organization {name: $company})
MERGE (u)-[t:TRACKS]->(o)
  ON CREATE SET t.since = datetime(), t.statedAs = $rawText;

// "I focus on graph databases" → canonicalize to the IndustryCategory node.
MATCH (u:User {userId: $userId})
MATCH (c:IndustryCategory {name: $category})
MERGE (u)-[f:FOCUSES_ON]->(c)
  ON CREATE SET f.statedAs = $rawText;
```

Storing the user's original words on the edge (`statedAs`) is what lets the
agent later say *why* in the analyst's own language instead of paraphrasing.

Once those edges exist, the daily-brief query — "what should I read that I'm
not already following?" — stops being a vector lookup plus a post-filter and
becomes one traversal:

```cypher
MATCH (u:User {userId: $userId})-[:FOCUSES_ON]->(cat:IndustryCategory)
MATCH (o:Organization)-[:HAS_CATEGORY]->(cat)
WHERE NOT (u)-[:TRACKS]->(o)                       // novelty: not already followed
MATCH (a:Article)-[:MENTIONS]->(o)
  WHERE a.date >= date() - duration({days: 7})
RETURN o.name                        AS company,
       collect(DISTINCT cat.name)    AS becauseYouFollow,
       collect(DISTINCT a.title)[0..3] AS headlines
ORDER BY size(headlines) DESC
LIMIT 10;
```

`becauseYouFollow` is the explanation, read off the edges that produced the
row. It cannot drift from the recommendation, because it *is* the
recommendation — the same property that makes the reasoning trail in
`hooks/persist-reasoning.ts` worth recording, applied to retrieval.

**Why the shipped project does not do this.** Two hard reasons, both
environmental rather than architectural:

1. `demo.neo4jlabs.com` is a shared read-only instance. [`lib/neo4j.ts`](industry-research-agent/agent/lib/neo4j.ts)
   pins `routing: "READ"` deliberately — there is no `MERGE` to be had.
2. The hosted NAMS workspace is a different database from the demo graph, and
   no traversal crosses databases.

Both dissolve the moment you bring your own Aura instance: load your domain
data, point `NAMS_ENDPOINT` at NAMS running against it, and the bridge writes
above are ordinary tool code. The memory wiring in
[Extension points](#extension-points) does not change at all — this is a
deployment topology decision, not a different integration.

This is the pattern William Lyon's
[post](https://lyonwj.com/blog/agent-memory-with-eve-and-nams) is built around,
and it is the one part of that write-up this project cannot demonstrate on the
shared demo database.

---

## Challenges and gaps

### 1. Retrieval is lexical, not semantic — moderate

NAMS search matches keywords with AND semantics; scores come back `undefined`.
A paraphrased query misses a memory that is definitely stored. Reproduced live:

```
"Search your memory for 'European'"       → 1 memory, long-term/user_preference
"What geography do I restrict research to?" → nothing
```

*Impact:* `tools` mode is the weakest of the three, because the model writes the
query and models paraphrase. `wrap` and `hooks` retrieve against the user's own
words and hit far more often.
*Workaround:* prefer `wrap`/`hooks`; describe the tool as taking keywords, not
questions. The provider already fans a query out into single keywords.

### 2. Long-term entities are workspace-scoped, not user-scoped — blocking for multi-tenant

`memoryScope` correctly scopes conversations by user, but facts written to the
long-term graph carry no user id, so users sharing a workspace read each other's
stored facts. Reproduced in this project while testing the three modes. Four
`DEMO_USER_ID` values each stored one preference in the same workspace; the
fourth user then asked what they focus on:

```
> What do I focus on? Answer in one sentence.
You focus on European companies, especially semiconductor supply chains,
undersea cable operators, and Nordic fintech.
```

Only "Nordic fintech" belonged to that user. The other three came from the other
test identities, and the agent presented all four as one profile without
hesitation.

*Workaround:* **one NAMS workspace per tenant**, passed as `NAMS_WORKSPACE_ID`.
Tracking upstream at [neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory).

### 3. Entity extraction is asynchronous — minor

A fact stored this turn is not immediately searchable in the long-term graph.
Short-term conversation memory is available immediately, so same-session recall
still works; cross-session recall of a just-stored fact may lag.

### 4. Hooks are at-least-once — minor

An interrupted turn re-runs its step and re-emits its events, so a retention
hook can store an exchange twice. eve's guidance is to key stored content on
`event.meta.id`; NAMS exposes no dedupe key, so budget for occasional
duplicates.

### 5. Non-string tool-call results are silently discarded — minor, but silent

`reasoning.recordToolCall(stepId, name, args, { result })` accepts any JSON
value for `result` and returns 200, but stores `""` for anything that is not a
string. Verified live against three calls on one step:

```
obj_result     -> ""                                        // { name: "Neo4j", … }
str_result     -> "{\"name\":\"Neo4j\",\"ceo\":\"Emil Eifrem\"}"  // same object, stringified
plain_string   -> "Emil Eifrem"
```

No error, no warning — the provenance is simply gone at read time. Arguments
(`arguments`) are unaffected and round-trip as objects, which makes the
asymmetry easy to miss.

*Workaround:* `serializeToolResult()` in [`lib/nams.ts`](industry-research-agent/agent/lib/nams.ts)
stringifies and length-caps before the write, and `ReasoningToolCall.result` is
typed `string` so the constraint is enforced at compile time rather than
discovered in the data.

### 6. Tool calls read back without their `stepId` — cosmetic

`getTraceByConversation` returns `stepId: undefined` on every tool call even
though the link exists — `explainStep(stepId)` resolves the same calls
correctly. Group by step through `explainStep`, not by reading `stepId`.

### 7. No packaged extension yet — moderate

Every consumer wires the three files by hand. eve's extension system is built
for exactly this (`eve extension init`), and the registry distributes such
packages via `eve add`. See below.

---

## Additional integration opportunities

### 1. Ship `@neo4j-labs/nams-eve` as a registry extension

eve extensions package tools, hooks, instruction fragments, and connections
behind a configured mount. A memory extension is the archetypal case — eve's own
docs use it as the example: *"A memory extension could use hooks to capture
context and tools to recall it."*

Consumer-side install would collapse this whole integration to:

```bash
eve add @neo4j-labs/nams
```

```ts title="agent/extensions/nams.ts"
import nams from "@neo4j-labs/nams-eve";

export default nams({
  apiKey: process.env.NAMS_API_KEY!,
  workspaceId: process.env.NAMS_WORKSPACE_ID,
});
```

The registry item is a small shadcn-format JSON document (dependencies,
`envVars`, and the mount file target). The [`extension/arcana`](https://vercel.com/docs/eve/install-integrations)
item is 20 lines. Official-catalog contributions go through an issue plus the
[registry contribution guide](https://github.com/vercel/eve/blob/main/CONTRIBUTING.md).
This would be the first **graph** memory in the gallery.

### 2. NAMS memory as a registry connection — the fastest path

`connection/mem0` is already in the catalog, and it is nothing but an MCP
connection plus a Connect OAuth mount. NAMS already publishes an MCP server, so
the same item shape applies with a plain bearer key. Verified live against
`https://memory.neo4jlabs.com/mcp`:

```
initialize  → 200  {"name":"nams-memory","version":"0.1.0"}   (Streamable HTTP)
tools/list  → 200  35 tools (26 memory_*, 9 workspace_*)
```

Which makes the whole integration this file:

```ts title="agent/connections/nams.ts"
import { defineMcpClientConnection } from "eve/connections";

export default defineMcpClientConnection({
  url: "https://memory.neo4jlabs.com/mcp",
  description: "Neo4j Agent Memory: store and recall persistent memory as a graph.",
  auth: { getToken: async () => ({ token: process.env.NAMS_API_KEY! }) },
  tools: { allow: ["memory_get_context", "memory_add_messages", "memory_add_entity"] },
});
```

Two caveats before shipping it. The surface includes destructive
`workspace_delete` / `workspace_reprovision`, so `tools.allow` is not optional
here. And no header binds a workspace — use a workspace-bound key or pass
`workspace_id` per call via `toolCall.providedArguments`.

This is deliberately *not* wired into the example project: it would register
memory tools alongside whichever of the three modes is active and double-handle
every turn. It is the right shape for a registry entry, not a fourth mode.

The [Neo4j MCP server](https://github.com/neo4j/mcp) fits the same slot for the
knowledge graph itself, giving eve agents schema-driven Cypher against any Aura
instance.

### 3. Memory as a queryable graph

Because memories are Neo4j nodes, the same workspace can be traversed by Neo4j
Browser, Bloom, or an MCP connection — so an agent can answer "why did you
recommend that?" by naming a path rather than generating a plausible reason.
Co-locating memory with domain data turns recommendation, constraint filtering,
and explanation into one Cypher query instead of a cross-system join.

### 4. Channels as identity

Slack, Discord, Teams, Telegram, and Linear channels attach a user principal for
the human sender automatically. `eve add slack` therefore gives correctly scoped
per-user memory with no additional auth code — a strong demo of memory that
follows a person across surfaces.

---

## Status

- ✅ Transparent memory via the model wrapper (`wrap`)
- ✅ Recall via dynamic instructions, retention via hooks (`hooks`)
- ✅ Model-driven memory tools (`tools`)
- ✅ Reasoning steps and tool provenance recorded in every mode
- ✅ Typed graph tools over the Neo4j driver
- ✅ `eve build` bundles the driver and provider with no `externalDependencies`
- ✅ Deploys to Vercel; verified fail-closed auth on the built output
- ✅ Cross-session recall covered by an eval
- ⚠️ Lexical-only retrieval; no vector search in NAMS today
- ⚠️ Long-term memory is workspace-scoped — one workspace per tenant
- ⚠️ Non-string tool-call results silently stored as `""` — serialize first
- ❌ Memory and domain data live in separate databases; no bridge edges (see
  [Co-locating memory and domain data](#co-locating-memory-and-domain-data))
- ❌ No published eve extension or registry entry yet
- 🔄 eve is in beta; APIs may change before GA

## Effort Score: 3/10

Transparent memory is one dynamic resolver in `agent.ts`. Most of the work is
deciding where the principal comes from, not writing memory code.

## Impact Score: 9/10

eve is Vercel's flagship agent framework and ships with no long-term memory of
its own, pointing users at an integration gallery that currently has no graph
option. The extension slot is designed for precisely this.

---

## Resources

- [Give Your Vercel Eve Agent a Memory](https://lyonwj.com/blog/agent-memory-with-eve-and-nams) — William Lyon on the same stack, built around [TrailGraph](https://github.com/johnymontana/trailgraph)
- [eve docs](https://vercel.com/docs/eve) · [GitHub](https://github.com/vercel/eve) · [Integrations](https://vercel.com/docs/eve/install-integrations)
- [NAMS](https://memory.neo4jlabs.com) · [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) · [`@neo4j-labs/agent-memory`](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Neo4j MCP server](https://github.com/neo4j/mcp)
- [`../vercel-agent/`](../vercel-agent/) — the same memory package on the Vercel AI SDK directly
- Demo database: `neo4j+s://demo.neo4jlabs.com:7687` (companies/companies)
