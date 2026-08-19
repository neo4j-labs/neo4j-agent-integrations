# Vercel eve + Neo4j

Persistent, graph-backed memory for [eve](https://vercel.com/docs/eve), Vercel's
open-source framework for durable backend agents.

**[→ Tutorial: build and deploy an eve agent on Vercel with Neo4j memory](TUTORIAL.md)**
**[→ Working project: `industry-research-agent/`](industry-research-agent/)**
**[→ Demo runbook: setup, questions, and how to show it](DEMO_RUNBOOK.md)**
**[→ The pitch to Vercel and objection handling](PITCH_AND_DEMO.md)**

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

eve exposes four places memory can attach. This project uses the second for
memory itself, the third for the bridge tools, and the fourth for read-only
traversal of the memory graph; the first is documented as an option not taken,
because the point of this page is to map the whole surface.

**All of them go through one gateway.** `agent/lib/memory-gateway.ts` is the
only file in the project that calls the NAMS SDK; hooks, tools, dynamic
instructions, and `agent.ts` all reach memory through `memory.for(scope)`. It
hands out **one `MemoryClient` per user id** and reuses it, for three reasons:

- `resolveConversation` caches the user's conversation id in provider state
  keyed by the client *instance*, so a fresh client per call means a wasted
  `list_conversations` round trip before every recall and every store — three
  per turn in `hooks` mode.
- `workspaceId` is fixed at client construction, so a workspace-per-tenant
  policy (the only hard isolation NAMS offers — see
  [Challenges](#2-long-term-entities-are-workspace-scoped-not-user-scoped--blocking-for-multi-tenant))
  is only expressible with a client per tenant. `workspaceIdFor(userId)` in
  `lib/nams.ts` is that seam.
- The map key is the namespace, and the map is bounded (`NAMS_CLIENT_CACHE`,
  default 256, LRU).

```ts
const mem = memory.for(memoryScope(ctx));   // namespace = userId
await mem.recall(query, 6);
await mem.remember({ content, type: "interaction" });
await mem.rememberReasoning(steps);
```

### 1. The model (`agent/agent.ts`) — available, not used here

`defineAgent({ model })` accepts a resolved AI SDK `LanguageModel`, and
`defineDynamic` can resolve one per step. Since `createNams().wrap(model, scope)`
produces a memory-wrapped `LanguageModelV4`, memory can be made a property of
the model — invisible to the harness, tools, and channels:

```ts
model: defineDynamic({
  fallback: "openai/gpt-5.4",
  events: {
    "step.started": (_event, ctx) =>
      createNams(config).wrap(gateway("openai/gpt-5.4"), { userId: userIdFrom(ctx) }),
  },
}),
```

It is the shortest way to add memory to an agent you would rather not modify,
and the right choice if that is your constraint. **This project does not use
it**, because it stores every turn with no say in what is worth keeping, and
because putting retention in a hook costs one extra file and makes the decision
explicit. `agent.ts` here is a plain model id.

Constraints worth knowing if you do take this route: only `step.started` may
return a live model object (session- and turn-scoped selections are serialized,
so they must be id strings), and `fallback` must stay a plain id because it
anchors build-time routing and context-window metadata.

### 2. Instructions and hooks (`agent/instructions/`, `agent/hooks/`) — used here

How this project wires memory, the split a packaged memory extension would
ship, and what eve's own
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
store call in `try`/`catch`. This is the shape to ship because it is the only
one where retention does not depend on the model choosing to save: a tool-driven
agent remembers enthusiastically for a few turns and then stops.

### 3. Tools (`agent/tools/`) — the domain surface, not the retention path

`defineTool` files, or a `defineDynamic` map. Memory *can* be exposed this way
as `recall_memory` / `remember`, which is the only shape visible in the TUI and
in traces, and the only one that supports "forget that" — but it is also the
only one where forgetting to call a tool means forgetting the user, so this
project does not retain that way. The tool surface is deliberately small —
`search_news` and nothing else — and everything the model can reach beyond it
is the read-only MCP connection below.

With dynamic tools, `execute` **must be an inline function expression** — eve
reconstructs it from its closure on replay and does not detect
`execute: namedFn`, which silently breaks after a resume.

### 4. Connections (`agent/connections/`) — read-only traversal of memory

`defineMcpClientConnection` points eve at any Streamable-HTTP or SSE MCP server,
exposing its tools as `<connection>__<tool>` and keeping the URL and credentials
out of model context entirely.

NAMS publishes an MCP server alongside its REST API, so
[`connections/memory-graph.ts`](industry-research-agent/agent/connections/memory-graph.ts)
mounts it as a way for the model to *walk* memory it is not allowed to write:

```ts title="agent/connections/memory-graph.ts"
export default defineMcpClientConnection({
  url: process.env.NAMS_MCP_URL ?? "https://memory.neo4jlabs.com/mcp",
  description: "The agent's own long-term memory as a graph. […] Read-only.",
  auth: { getToken: async () => ({ token: process.env.NAMS_API_KEY! }) },
  tools: {
    allow: [
      "memory_search_entities",
      "memory_get_entity_by_name",
      "memory_get_entity_history",
      "memory_get_trace",
      "memory_explain_decision",
    ],
  },
});
```

Three things that surface generalizes:

- **`tools.allow`, not `tools.block`.** The server publishes 48 tools (verified
  live against `tools/list`): 26 `memory_*`, 13 `skill_*`, 9 `workspace_*`. The
  last group includes `workspace_delete` and `workspace_reprovision`, so an
  enumerated allow-list is not optional.
- **No write tools.** `memory_add_messages` here would give the model a second,
  optional path to store a turn `hooks/persist-turn.ts` already stores — the
  "did it remember?" coin-flip the hook exists to remove. Retention is the
  hook's job; the connection reads.
- **`workspace_id` via `toolCall.providedArguments`.** Every NAMS MCP tool
  accepts an optional `workspace_id` and no request header binds one, so left
  alone it appears in the model-facing input schema — a `userId` tool parameter
  one level out. Declaring it as an application-provided argument makes eve
  strip it from the schema and inject `workspaceIdFor(userId)` at call time.

For the domain graph, the [Neo4j MCP server](https://github.com/neo4j/mcp) fits
the same slot when you want schema-driven Cypher. The example project uses typed
`defineTool` files against the driver instead — narrower surface, no server to
run, and the model picks an edge rather than writing Cypher.

### Channels (`agent/channels/`) — identity, for free

Not a memory attachment point, but the cheapest way to satisfy the one rule the
others depend on. [`channels/eve.ts`](industry-research-agent/agent/channels/eve.ts)
needs an `AuthFn` you write, and `ctx.session.auth` is what `memoryScope` reads.
Platform channels derive the principal from the inbound event instead — a
`principalId` qualified by workspace and a `principalType` of `"user"` for a
human, `"service"` for a bot, which `memoryScope` refuses — so adding one scopes
memory per sender with no memory code in the channel file.

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
│           ▼              ┌── memory ─────────────────────────┐  │
│  agent/agent.ts ─────────┤ instructions/memory.ts   recall    │  │
│    plain model id        │ hooks/persist-turn.ts    retention │  │
│           │              │ hooks/persist-reasoning  provenance│  │
│           │              └───────────────┬───────────────────┘  │
│           │                all via lib/memory-gateway.ts        │
│           ▼                   one MemoryClient per userId       │
│  harness ── tool loop                    │                      │
│    search_news       full-text over the news graph              │
│    memory-graph__*  read-only MCP traversal of memory           │
└───────────┬──────────────────────────────┼──────────────────────┘
            │ bolt (read-only by default)  │ HTTPS
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
│   ├── agent.ts                    ← model only; memory lives in hooks
│   ├── instructions.md             ← research + memory system prompt
│   ├── channels/eve.ts             ← auth walk = memory boundary
│   ├── connections/memory-graph.ts ← NAMS MCP, read-only, allow-listed
│   ├── instructions/memory.ts      ← recall, resolved on turn.started
│   ├── hooks/persist-turn.ts       ← retention, flushed on turn.completed
│   ├── hooks/persist-reasoning.ts  ← reasoning steps + tool provenance
│   ├── tools/
│   │   └── search_news.ts          ← full-text over article chunks
│   └── lib/
│       ├── memory-gateway.ts       ← the only file that calls the NAMS SDK
│       ├── nams.ts                 ← config, workspace policy, pure helpers
│       ├── scope.ts                ← memory identity from verified session auth
│       ├── bridge.ts               ← (:User)→domain edges, opt-in via NEO4J_BRIDGE
│       ├── model.ts                ← AI Gateway or direct provider
│       └── neo4j.ts                ← driver; reads always, writes only when bridged
└── evals/
    ├── graph/news-search.eval.ts
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

### How memory is wired

One shape, three files, all reaching NAMS through the gateway.

| File | eve primitive | Event | Job |
|---|---|---|---|
| `instructions/memory.ts` | dynamic instructions | `turn.started` | recall — injects the user's memories as prompt *data* |
| `hooks/persist-turn.ts` | hook | `message.received` → `message.completed` → `turn.completed` | retention — one write per exchange |
| `hooks/persist-reasoning.ts` | hook | `actions.requested` / `action.result` / `reasoning.completed` → `turn.completed` | provenance — reasoning steps and tool calls |

The retrieval query is the user's own words, and storage is driven by the
runtime rather than by the model — neither depends on a tool call the model
might skip. Retrieval is lexical (see
[Challenges](#1-retrieval-is-lexical-not-semantic--moderate)), which is the
second reason recall belongs on `turn.started`: it searches what the user said,
not a model's paraphrase of it.

**Reasoning memory is independent of the other two.** NAMS's third memory type
records *why* the agent answered as it did — one step per reasoning block, with
the tool calls that step invoked hanging off it. Nothing else writes it, so
[`hooks/persist-reasoning.ts`](industry-research-agent/agent/hooks/persist-reasoning.ts)
never double-stores a turn. It buffers `actions.requested` / `action.result` /
`reasoning.completed` and flushes once on `turn.completed` — a step's tool calls
are only known after its reasoning block completes, and `recordToolCall` needs
the id of the step it belongs to. Set `NAMS_REASONING=off` to disable; it costs
one extra round trip per turn.

This is what `retrieveMemories`' fourth source reads, and what makes "why did
you recommend that?" answerable from recorded provenance. It uses
`findExistingConversation`, never `resolveConversation`: a trace is provenance
for a conversation that already happened and must never be the thing that
creates one.

```ts
const mem = memory.for(memoryScope(ctx));   // every path starts here

// recall     (instructions/memory.ts, turn.started)
defineInstructions({ markdown: renderMemories(await mem.recall(event.data.message)) })
// retention  (hooks/persist-turn.ts, turn.completed)
await mem.remember({ content, type: "interaction" })
// provenance (hooks/persist-reasoning.ts, turn.completed)
await mem.rememberReasoning(steps)
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
`MemoryClient`, or `NAMS_ENDPOINT` here), load your domain graph into it, set
`NEO4J_BRIDGE=on`, and write a **bridge edge** from the memory graph's `User` to
the real entity every time you store a preference. That is
[`agent/lib/bridge.ts`](industry-research-agent/agent/lib/bridge.ts). Its
`linkInterest` and `dailyBrief` are what a `track_interest` / `daily_brief`
tool pair calls — registered with `defineDynamic` and gated on `NEO4J_BRIDGE`,
which is how this project shipped them before the tool surface was cut back to
`search_news`:

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

Note that the `User` is `MERGE`d but the domain node is only ever `MATCH`ed: a
misspelled company must fail to link, not quietly create a second
`Organization` that shadows the real one. `linkInterest` returns near-miss
suggestions in that case so the agent asks instead of guessing.

Storing the user's original words on the edge (`statedAs`) is what lets the
agent later say *why* in the analyst's own language instead of paraphrasing.

Once those edges exist, the daily-brief query — "what should I read that I'm
not already following?" — stops being a vector lookup plus a post-filter and
becomes one traversal:

```cypher
CALL {
  MATCH (a:Article) WHERE a.date IS NOT NULL AND a.date <= datetime()
  RETURN max(a.date) AS newest
}
WITH coalesce(newest, datetime()) AS anchor              // "recent" relative to the data
MATCH (u:User {userId: $userId})-[:FOCUSES_ON]->(cat:IndustryCategory)
MATCH (o:Organization)-[:HAS_CATEGORY]->(cat)
WHERE NOT (u)-[:TRACKS]->(o)                             // novelty: not already followed
MATCH (a:Article)-[:MENTIONS]->(o)
  WHERE a.date >= anchor - duration({days: 90})
RETURN o.name                          AS company,
       collect(DISTINCT cat.name)      AS becauseYouFollow,
       collect(DISTINCT a.title)[0..3] AS headlines
ORDER BY size(headlines) DESC
LIMIT 10;
```

`becauseYouFollow` is the explanation, read off the edges that produced the
row. It cannot drift from the recommendation, because it *is* the
recommendation — the same property that makes the reasoning trail in
`hooks/persist-reasoning.ts` worth recording, applied to retrieval.

**Why this is off by default.** Two hard reasons, both environmental rather
than architectural:

1. `demo.neo4jlabs.com` is a shared read-only instance. `writeQuery` in
   [`lib/neo4j.ts`](industry-research-agent/agent/lib/neo4j.ts) refuses unless
   `NEO4J_BRIDGE=on`, and `readQuery` pins `routing: "READ"` — there is no
   `MERGE` to be had against the demo graph.
2. The hosted NAMS workspace is a different database from the demo graph, and
   no traversal crosses databases.

Both dissolve the moment you bring your own Aura instance: load your domain
data, point `NAMS_ENDPOINT` at NAMS running against it, flip `NEO4J_BRIDGE=on`,
and the bridge tools are worth registering again. The memory wiring in
[Extension points](#extension-points) does not change at all — this is a
deployment topology decision, not a different integration. Walkthrough:
[TUTORIAL → Step 8](TUTORIAL.md#step-8--point-nams-at-your-own-neo4j-and-write-bridge-edges).

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

*Impact:* a memory *tool* is the weakest shape, because the model writes the
query and models paraphrase. Recall on `turn.started` retrieves against the user's own
words and hit far more often.
*Workaround:* keep recall out of the model's hands; describe any memory tool you do add as taking keywords, not
questions. The provider already fans a query out into single keywords.

### 2. Long-term entities are workspace-scoped, not user-scoped — blocking for multi-tenant

`memoryScope` correctly scopes conversations by user, but facts written to the
long-term graph carry no user id, so users sharing a workspace read each other's
stored facts. Reproduced in this project during testing. Four
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

*Workaround:* **one NAMS workspace per tenant.** Return the tenant's workspace
id from `workspaceIdFor(userId)` in
[`lib/nams.ts`](industry-research-agent/agent/lib/nams.ts); the gateway builds
that tenant a client bound to it. This only works because the gateway keeps one
client per user — `workspaceId` is fixed at client construction and cannot be
varied per request on a shared client, which is the third reason
[the gateway exists](#extension-points). Scoping in application code is not
enough on its own.
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
tools/list  → 200  35 tools with a key (26 memory_*, 9 workspace_*)
            → 200  48 anonymously (the same, plus 13 skill_*)
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
here. And no request header binds a workspace — use a workspace-bound key, or
pass `workspace_id` per call via `toolCall.providedArguments`, which also strips
it from the schema the model sees. The shipped
[`connections/memory-graph.ts`](industry-research-agent/agent/connections/memory-graph.ts)
does the latter.

The example project mounts this server, but **read-only**
([`connections/memory-graph.ts`](industry-research-agent/agent/connections/memory-graph.ts)):
allowing the write tools would register memory tools alongside the retention
hook and double-handle every turn. A registry entry would make the same
distinction — a read surface the model can traverse, with retention still owned
by the extension's hook.

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

Platform channels attach a user principal for the human sender automatically, so
a memory scope derived from `ctx.session.auth` gives correctly scoped per-user
memory with no additional auth code — memory that follows a person across
surfaces, for free.

---

## Status

- ✅ Recall via dynamic instructions, retention via hooks — no memory tool the model can forget to call
- ✅ One `MemoryClient` per user behind a single gateway; the SDK has one call site
- ✅ Reasoning steps and tool provenance recorded
- ✅ Typed graph tools over the Neo4j driver
- ✅ Bridge edges from `(:User)` to domain nodes, behind `NEO4J_BRIDGE=on`
- ✅ NAMS MCP mounted as a read-only connection, allow-listed to 5 of 48 tools
- ✅ `eve build` bundles the driver and provider with no `externalDependencies`
- ✅ Deploys to Vercel; verified fail-closed auth on the built output
- ✅ Cross-session recall covered by an eval
- ⚠️ Lexical-only retrieval; no vector search in NAMS today
- ⚠️ Long-term memory is workspace-scoped — one workspace per tenant
- ⚠️ Non-string tool-call results silently stored as `""` — serialize first
- ⚠️ Bridge edges need your own Neo4j; the shared demo instance is read-only, so
  they are off by default (see
  [Co-locating memory and domain data](#co-locating-memory-and-domain-data))
- ❌ No published eve extension or registry entry yet
- 🔄 eve is in beta; APIs may change before GA

## Effort Score: 3/10

Recall is one dynamic instructions file, retention is one hook, and both go
through a gateway of about 150 lines. Most of the work is deciding where
the principal comes from, not writing memory code.

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
