# Vercel eve + Neo4j: Give Your Agent a Memory

This project shows how to give an AI agent built with **eve** (Vercel's agent
framework) a real, long-term memory using **NAMS** (Neo4j Agent Memory System)
and **Neo4j** (a graph database).

**[→ Working project: `industry-research-agent/`](industry-research-agent/)**

---

## The three pieces, in plain words

If you are new to any of these, start here.

**eve** is an open-source framework from Vercel for building backend AI agents.
You describe your agent as files in an `agent/` folder — its instructions, its
tools, how users connect to it — and eve turns those files into a running
service. Its big feature is *durability*: a conversation (a "session") survives
crashes, redeploys, and even days of inactivity. It runs locally, on Vercel, or
on any Node.js host.

**Neo4j** is a graph database. Instead of tables, it stores *nodes* (things:
a company, a person, an article) and *relationships* between them (Neo4j calls
these edges — e.g. `(Article)-[:MENTIONS]->(Organization)`). You query it with
a language called **Cypher**. Graphs are good at questions that follow
connections: "which companies compete with the ones this user tracks?"

**NAMS** (Neo4j Agent Memory System, [memory.neo4jlabs.com](https://memory.neo4jlabs.com))
is a hosted memory service for agents, built on Neo4j. You send it what
happened in a conversation; it stores three kinds of memory:

- **short-term** — the conversation thread itself
- **long-term** — facts extracted from conversations, stored as a graph of
  entities and relationships ("Alex covers the graph database sector")
- **reasoning** — a record of *why* the agent did what it did: each reasoning
  step and the tool calls it made

You get a free API key, and you talk to it through the
`@neo4j-labs/agent-memory` SDK or its MCP server.

**How they fit together:** eve runs the agent, NAMS stores and recalls its
memory, and Neo4j is the database underneath that makes the memory a graph you
can query and inspect.

**Official resources**
- eve: https://vercel.com/docs/eve · source: https://github.com/vercel/eve (Apache-2.0)
- eve docs are also bundled in the installed package at `node_modules/eve/docs/`
- NAMS: https://memory.neo4jlabs.com
- Neo4j: https://neo4j.com

---

## Why does an eve agent need this?

eve keeps a session alive for a long time, but **a session is not memory**.
eve's own docs say so — session state
("`defineState`") lives and dies with the session:

> Anything that has to outlive the session, be shared across sessions or users,
> or be queried independently of a turn belongs in an external store.

For that external store, eve points at its integration gallery. At the time of
writing, the gallery has three memory options (`mem0`, `upstash-agentkit`,
`arcana`) — all key/value or vector stores. **None of them stores memory as a
graph.**

Why does a graph matter for memory? Because most things worth remembering are
*connected*: this user follows these sectors, which contain these companies,
which compete with those companies, which were mentioned in these articles. A
flat store gives you back the facts that matched your search. A graph can also
give you what those facts are connected to — and it can *explain* a recall by
naming the path that produced it.

---

## The example: Industry Research Agent

The repo's [reference agent](../../EXAMPLE_AGENT.md), built on eve in
[`industry-research-agent/`](industry-research-agent/).

**Scenario:** an analyst asks about companies, competitors, and news. The agent
answers from a public Neo4j "Company News" graph (about 250k organizations,
people, and articles) — and remembers each analyst's name, beat, tracked
companies, and preferences across sessions and deployments.

### Architecture

```
   Analyst
      │  POST /eve/v1/session          GET /eve/v1/session/:id/stream
      ▼
┌─────────────────────────────────────────────────────────────────  ┐
│  eve runtime (local, Vercel, or any Node host)                    │
│                                                                   │
│  agent/channels/eve.ts   who is calling? → ctx.session.auth       │
│           │                                                       │
│           ▼              ┌── memory ───────────────────────── ┐   │
│  agent/agent.ts ─────────┤ instructions/memory.ts   recall    │   │
│    plain model id        │ hooks/persist-turn.ts    store     │   │
│           │              │ hooks/persist-reasoning  why-trail │   │
│           │              └───────────────┬─────────────────── ┘   │
│           │                all via lib/memory-gateway.ts          │
│           ▼                   one MemoryClient per userId         │
│  model ── tool loop                      │                        │
│    search_news       full-text over the news graph                │
│    neo4j-graph__*    Neo4j MCP: get-schema, read-cypher,          │
│                      list-gds-procedures                          │
│    memory-graph__*   read-only browsing of the memory graph       │
└───────────┬──────────────────────────────┼──────────────────────  ┘
            │ bolt (read-only)             │ HTTPS
            ▼                              ▼
   ┌──────────────────────┐   ┌────────────────────────────────── ┐
   │ Company News graph   │   │ NAMS — memory.neo4jlabs.com       │
   │ demo.neo4jlabs.com   │   │  short-term  conversation thread  │
   │ 250k orgs, people,   │   │  long-term   entities + relations │
   │ articles, embeddings │   │  reasoning   step records         │
   └──────────────────────┘   └──────────────┬─────────────────── ┘
                                             │
                                    Neo4j AuraDB
```

### Project layout

Four systems meet in one directory:

```
  EVE  ──────────►  NAMS  ──────────►  Neo4j MCP  ──────────►  Neo4j
  the runtime       the memory         the graph tools         companies db
```

```
industry-research-agent/
├── agent/
│   ├── README.md                   ← every folder below, and what it holds
│   ├── agent.ts                    ← model only; memory lives in hooks
│   ├── instructions.md             ← the system prompt
│   ├── channels/
│   │   ├── eve.ts                  ← HTTP: decides who the caller is
│   │   └── slack.ts                ← Slack: identity from the Slack sender
│   ├── connections/
│   │   ├── memory-graph.ts         ← NAMS MCP server, read-only
│   │   └── neo4j-graph.ts          ← Neo4j MCP server, read-only
│   ├── instructions/
│   │   └── memory.ts               ← recall: runs at the start of every turn
│   ├── hooks/
│   │   ├── persist-turn.ts         ← store: runs at the end of every turn
│   │   └── persist-reasoning.ts    ← records why the agent did what it did
│   ├── tools/
│   │   └── search_news.ts          ← full-text search over news articles
│   ├── skills/
│   │   └── research_rules.md       ← query/citation rules, loaded on demand
│   └── lib/
│       ├── memory-gateway.ts       ← the only file that calls the NAMS SDK
│       ├── nams.ts                 ← config, env flags, memory identity
│       ├── graph-extractor.ts      ← turns stored text into graph entities
│       ├── model.ts                ← AI Gateway or direct provider
│       └── neo4j.ts                ← read-only queries to the news graph
└── evals/
    ├── graph/news-search.eval.ts
    └── memory/cross-session-recall.eval.ts
```

**17 files.** Detailed folder-by-folder notes are in
[`agent/README.md`](industry-research-agent/agent/README.md).

---

## How memory works here

The core idea is simple: **the runtime remembers, not the model.**

Many memory demos give the model two tools — `save_memory` and `recall_memory` —
and hope it calls them. In practice it calls them for a few turns and then
stops. So this project attaches memory to events eve fires on every turn,
where the model has no say:

| File | eve feature | When it runs | What it does |
|---|---|---|---|
| `instructions/memory.ts` | dynamic instructions | start of every turn | **recall** — searches NAMS with the user's message and puts matching memories into the prompt |
| `hooks/persist-turn.ts` | hook | end of every turn | **store** — writes the user/assistant exchange to NAMS |
| `hooks/persist-reasoning.ts` | hook | end of every turn | **why-trail** — records the agent's reasoning steps and tool calls |

All three go through one small class, the **gateway**
(`agent/lib/memory-gateway.ts`). It is the only file in the project that calls
the NAMS SDK, and its whole API is:

```ts
const mem = memory.for(memoryScope(ctx));   // "whose memory?" — one client per user
await mem.recall(query, 6);                 // read
await mem.remember({ content, type: "interaction" });  // write
await mem.rememberReasoning(steps);         // record the why-trail
```

Why one gateway, and one client per user?

- The SDK caches each user's conversation id *on the client object*. Reuse the
  client and recalls are fast; create a new client per call and every recall
  pays an extra network round trip first.
- A client is bound to one NAMS **workspace** when it is created. Giving each
  user (or each tenant) their own workspace is the only hard isolation NAMS
  offers today, and that is only possible
  with one client per user. `workspaceIdFor(userId)` in `lib/nams.ts` is where
  you plug that policy in.
- The cache of clients is bounded (`NAMS_CLIENT_CACHE`, default 250, oldest
  evicted first), so a long-lived server doesn't grow forever.

Two practical rules that apply to any eve memory hook:

- **A hook that throws fails the whole turn.** Memory is a nice-to-have, so
  every store call is wrapped in `try`/`catch` — if NAMS is down, the user
  still gets their answer.
- **Recall runs per *turn*, not per session**, so a fact stored on turn 1 is
  already in the prompt on turn 2.
- **Recall searches with the user's own words.** NAMS search is
  keyword-based, and the user's own nouns
  match stored text much better than a model's paraphrase of them would.

### Reasoning memory (the "why" trail)

NAMS's third memory type records *why* the agent answered the way it did — one
record per reasoning step, with the tool calls that step made attached.
`hooks/persist-reasoning.ts` collects tool calls during the turn and writes
them once at the end (a step's tool calls are only known once the step
finishes). This is what lets the agent answer "why did you recommend that?"
from an actual record instead of making up a plausible story. Set
`NAMS_REASONING=off` to disable it; it costs one extra request per turn.

---

## Where memory can attach to eve

eve gives you four places to plug memory in. This project uses **#2** for
memory itself and **#4** for read-only browsing; #3 holds one domain tool and
no memory; #1 was tried and reverted.

### 1. Wrap the model

The NAMS provider package can wrap any AI SDK model so that memory happens
invisibly inside every model call:

```ts
model: defineDynamic({
  fallback: "openai/gpt-5.4",
  events: {
    "step.started": (_event, ctx) =>
      createNams(config).wrap(gateway("openai/gpt-5.4"), { userId: userIdFrom(ctx) }),
  },
}),
```

This is the fastest way to add memory to an agent you don't want to modify. We
shipped it, tested it, and went back to plain hooks: the wrapper stores *every*
turn with no filtering, hides its own write failures, and records no reasoning
memory. `agent/agent.ts` here is just a plain model id.

(If you do use it: only the `step.started` event may return a live model
object, and `fallback` must stay a plain id string.)

### 2. Dynamic instructions + hooks — what this project uses

- **Recall** = a dynamic instruction that runs at the start of each turn and
  returns extra markdown for the prompt.
- **Store** = a hook that runs after eve has durably recorded the turn.

This is also what eve's own
[multi-tenant memory pattern](https://vercel.com/docs/eve/patterns/multi-tenant-memory)
recommends, and it's the shape a packaged memory extension would ship. Its key
property: remembering never depends on the model deciding to call a tool.

### 3. Tools — used for the domain, not for memory

You *can* expose memory as `recall_memory` / `remember` tools. It's the only
shape the user can see in the UI, and the only one that supports "forget that" —
but it's also the only one where the model forgetting to call a tool means
forgetting the user. This project keeps the tool surface small and read-only:
one tool, `search_news`.

### 4. MCP connections — mounted servers, read-only

**MCP** (Model Context Protocol) is a standard that lets an agent use tools
published by an external server. eve's `defineMcpClientConnection` mounts any
such server and exposes its tools to the model, keeping the URL and credentials
out of the model's view. This project mounts two:

- [`connections/neo4j-graph.ts`](industry-research-agent/agent/connections/neo4j-graph.ts)
  — the official [Neo4j MCP server](https://github.com/neo4j/mcp), so the
  model can read the graph's schema and run read-only Cypher without us writing
  those tools by hand.
- [`connections/memory-graph.ts`](industry-research-agent/agent/connections/memory-graph.ts)
  — the NAMS MCP server, so the model can *browse* its own memory graph. It is
  not allowed to write.

Three safety habits worth copying:

- **Use `tools.allow`, not `tools.block`.** The NAMS server publishes over 40
  tools (verified live), including ones that write and ones that can delete a
  whole workspace. An allow-list stays safe when the server adds new tools; a
  block-list doesn't.
- **No write tools from MCP.** Storing is the hook's job. Giving the model a
  second, optional way to store would bring back the "did it remember?"
  coin-flip the hook exists to remove.
- **Inject `workspace_id` from the app, not the model.** Every NAMS MCP tool
  accepts an optional `workspace_id`. Left alone, it shows up as a parameter
  the *model* fills in. Declaring it as an application-provided argument
  (`toolCall.providedArguments`) makes eve hide it from the model and inject
  the right value at call time.

### Also load-bearing: channels and skills

**Channels** (`agent/channels/`) are how users reach the agent (HTTP, Slack, …)
— and each channel decides *who the caller is*.

**Skills** (`agent/skills/`) are instructions loaded only when needed. Keeping
the 40-line querying procedure in a skill means the memory block injected each
turn isn't competing with it for the model's attention.

---

## Who is the user? (Authentication)

For a memory agent, this is the most important design decision: **the verified
caller identity is the memory scope.**

In eve, the channel file (`agent/channels/eve.ts`) runs an ordered list of
authenticators on each request and produces `ctx.session.auth`. That's where
the user id comes from — never from a tool argument. Why it matters: a tool
that accepts a `userId` parameter lets a prompt-injected document ask for
*someone else's* memory. An id derived from verified auth can't be talked into
that.

| Mechanism | Support | Notes |
|---|---|---|
| API keys / bearer | ✅ | `httpBasic()`, `jwtHmac()`, `jwtEcdsa()`, or a custom `AuthFn` |
| OIDC (any issuer) | ✅ | `oidc({ issuer, audiences, discoveryUrl })` |
| Vercel OIDC | ✅ | `vercelOidc()`; zero-config for Vercel-to-Vercel callers |
| OAuth 2.1 (outbound) | ✅ | `connect()` from `@vercel/connect/eve` |
| Anonymous | ⚠️ | `none()` only; otherwise fails closed in production |

Each authenticator may accept, skip, or reject. Put your app's own
authenticator first:

```ts
export default eveChannel({ auth: [appSession(), vercelOidc(), localDev()] });
```

Two rules to remember:

- **`principalId` must be stable for the same person forever.** It becomes the
  NAMS user id — change how you compute it and that user loses their memory.
- **Replace `placeholderAuth()` before production.** `eve init` scaffolds it,
  and it rejects everyone with a 401. Leaving it in means no caller works;
  deleting the auth walk instead means *every* caller shares one memory.

**NAMS auth** is simpler: one `nams_...` API key sent as a bearer token,
optionally bound to a workspace via `NAMS_WORKSPACE_ID`. Free keys at
[memory.neo4jlabs.com](https://memory.neo4jlabs.com).

---

## Getting started

### What you need

| Need | Notes |
|---|---|
| **Node 24+** | eve requires it — check with `node -v` |
| **A NAMS key** | free at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) → `NAMS_API_KEY`. Leave `NAMS_WORKSPACE_ID` blank if your key is already bound to a workspace — a wrong value makes every memory call fail with 403 while answers still stream |
| **A model credential** | `AI_GATEWAY_API_KEY` for any [AI Gateway model](https://vercel.com/ai-gateway/models), or `OPENAI_API_KEY`. Deployed on Vercel, project OIDC covers the Gateway and neither is needed |
| **Neo4j** | nothing to set up — `.env.example` points at a public read-only demo database |

> **Use a fresh NAMS workspace.** Long-term facts in NAMS are shared by
> everyone in a workspace.

### Quickstart

```bash
cd industry-research-agent
npm install
cp .env.example .env        # add NAMS_API_KEY + one model credential; leave NEO4J_* alone
npx eve info                # sanity check: 1 skill, 4 tools, 0 diagnostics
```

The whole demo is two commands:

```bash
npx eve invoke "My name is Alex and I cover the graph database sector."
npx eve invoke "What is my name and what sector do I cover?"
```

Here's the point: each `eve invoke` is a **separate session** — the second
command has no access to the first one's transcript, and no memory tool appears
in either trace. The only path between them is Neo4j: the hook stored the first
exchange because the turn happened, and recall injected it at the start of the
second. (Locally both commands run as `DEMO_USER_ID`; in production the
identity comes from the channel's auth.)

Then try the graph tools, one at a time:

```bash
npx eve invoke "What's been written about graph database funding?"        # search_news
npx eve invoke "What node labels and relationships does this graph have?" # neo4j-graph__get-schema
npx eve invoke "Who has invested in Neo4j?"                               # neo4j-graph__read-cypher
npx eve invoke "Which graph algorithms can this database run?"            # neo4j-graph__list-gds-procedures
```

`npm run dev` opens eve's terminal UI against the same agent.

### Over HTTP

`eve dev` serves on `http://127.0.0.1:2000`; `eve start` (built output) on `3000`.

```bash
curl -X POST http://127.0.0.1:2000/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"Who has invested in Neo4j?"}'
# {"ok":true,"sessionId":"wrun_...","status":"accepted"}

curl -N http://127.0.0.1:2000/eve/v1/session/<sessionId>/stream   # NDJSON, one event per line
```

No `Authorization` header needed locally — `localDev()` accepts the caller only
while running under `eve dev`. Against a deployment, the auth walk in
[`channels/eve.ts`](industry-research-agent/agent/channels/eve.ts) decides.

### Test

```bash
npx eve eval             # all evals — also the deploy gate
npx eve eval memory      # just evals/memory/
npm run typecheck        # tsc
```

The eval that matters is `memory/cross-session-recall`. It stores a fact, calls
`t.newSession()` to **throw the transcript away**, and then checks the agent
still knows the fact. If that passes, memory is real — not just a long context
window. `npx eve eval --url https://<deployment>` runs the same files against a
live deployment, so the same test is both the deploy gate and the production
smoke test.

### Deploy

```bash
npx eve link     # link or create the Vercel project, pull its env
npx eve deploy   # installs, runs `vercel deploy --prod`
```

Set `NAMS_API_KEY`, `AGENT_MODEL`, and the `NEO4J_*` values in the Vercel
project's environment. A plain model id routes through the AI Gateway using
project OIDC, so no model provider key is needed there.

And once more, because it's the one that bites: **replace `placeholderAuth()`
before real traffic** — see [Who is the user?](#who-is-the-user-authentication).

---

## The dataset

The tools read a public, read-only Neo4j demo database (no setup needed):

```env
NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687
NEO4J_USERNAME=companies
NEO4J_PASSWORD=companies
NEO4J_DATABASE=companies
```

Its schema, verified on the live instance:

```
(Organization)-[:IN_CITY]->(City)-[:IN_COUNTRY]->(Country)
(Organization)-[:HAS_CATEGORY]->(IndustryCategory)
(Organization)-[:HAS_CEO|HAS_BOARD_MEMBER]->(Person)
(Organization)-[:HAS_COMPETITOR|HAS_SUPPLIER|HAS_SUBSIDIARY|HAS_INVESTOR]->(Organization)
(Article)-[:MENTIONS]->(Organization)
(Article)-[:HAS_CHUNK]->(Chunk)
```

Indexes: `entity` (full-text over names), `news_fulltext` (full-text over
article text), `news` (vector, 1536 dimensions).

**One trap:** the `news` vector index was built with OpenAI's
`text-embedding-ada-002` model. Query it with embeddings from a *different*
model and you get confident nonsense — we measured a "graph database funding"
query returning articles about hate-speech moderation at ~0.54 similarity with
the wrong model, versus the right funding articles at ~0.92 with ada-002.
That's why the shipped `search_news` tool uses the full-text index instead: it
works no matter which model the agent runs on. If you want the vector version:

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

---

## Going further: memory and domain data in one database

Everything above keeps two databases: NAMS stores memory in its own hosted
instance, and the tools read the public news graph. That works, and it's the
right default with a hosted NAMS key — but the real payoff of *graph* memory
appears when memory and domain data live **in the same database**, connected by
edges.

The idea: point NAMS at a Neo4j instance you own (`NAMS_ENDPOINT`), load your
domain data into it, and whenever a user states a preference, write a **bridge
edge** from their `User` node to the real domain node:

```cypher
// "I track Neo4j" → link the user to the real Organization node.
MATCH (o:Organization {name: $company})
MERGE (u:User {userId: $userId})
MERGE (u)-[t:TRACKS]->(o)
  ON CREATE SET t.since = datetime(), t.statedAs = $rawText;

// "I focus on graph databases" → link to the IndustryCategory node.
MATCH (c:IndustryCategory {name: $category})
MERGE (u:User {userId: $userId})
MERGE (u)-[f:FOCUSES_ON]->(c)
  ON CREATE SET f.statedAs = $rawText;
```

Two details worth copying:

- The `User` is `MERGE`d (created if missing) but the domain node is only
  `MATCH`ed — a misspelled company name should fail to link, not quietly create
  a duplicate company node.
- `statedAs` keeps the user's original words on the edge, so the agent can
  later explain a recommendation in the user's own language.

Once those edges exist, "what should I read that I'm not already following?"
becomes a single query instead of a search plus filtering:

```cypher
CALL {
  MATCH (a:Article) WHERE a.date IS NOT NULL AND a.date <= datetime()
  RETURN max(a.date) AS newest
}
WITH coalesce(newest, datetime()) AS anchor              // "recent" relative to the data
MATCH (u:User {userId: $userId})-[:FOCUSES_ON]->(cat:IndustryCategory)
MATCH (o:Organization)-[:HAS_CATEGORY]->(cat)
WHERE NOT (u)-[:TRACKS]->(o)                             // new to the user
MATCH (a:Article)-[:MENTIONS]->(o)
  WHERE a.date >= anchor - duration({days: 90})
RETURN o.name                          AS company,
       collect(DISTINCT cat.name)      AS becauseYouFollow,
       collect(DISTINCT a.title)[0..3] AS headlines
ORDER BY size(headlines) DESC
LIMIT 10;
```

`becauseYouFollow` is the explanation, read straight off the edges that
produced the row — it can't drift from the recommendation, because it *is* the
recommendation.

**Why this isn't turned on here:** the demo database is shared and read-only
(`lib/neo4j.ts` has no write path at all), and the hosted NAMS workspace is a
different database, so no query can cross between them. Bring your own Neo4j
Aura instance and both reasons disappear — and none of the memory wiring above
changes.

---

## Ideas for the future

### 1. Package this as an eve extension

eve extensions bundle hooks, instructions, tools, and connections behind one
mount file. A memory extension is literally the example eve's docs use. With
one published, this whole integration becomes:

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

It would be the first **graph** memory in eve's integration gallery.

### 2. NAMS as a registry connection — the fastest path

The gallery's `connection/mem0` entry is just an MCP connection. NAMS already
runs an MCP server (verified live at `https://memory.neo4jlabs.com/mcp`), so
the same shape works with a plain bearer key — the whole integration is one
file:

```ts title="agent/connections/nams.ts"
import { defineMcpClientConnection } from "eve/connections";

export default defineMcpClientConnection({
  url: "https://memory.neo4jlabs.com/mcp",
  description: "Neo4j Agent Memory: store and recall persistent memory as a graph.",
  auth: { getToken: async () => ({ token: process.env.NAMS_API_KEY! }) },
  tools: { allow: ["memory_get_context", "memory_add_messages", "memory_add_entity"] },
});
```

Two cautions: the server's full tool list includes destructive
`workspace_delete` / `workspace_reprovision`, so the allow-list is not
optional; and no request header binds a workspace, so use a workspace-bound key
or inject `workspace_id` per call (as
[`connections/memory-graph.ts`](industry-research-agent/agent/connections/memory-graph.ts)
does). Note this project deliberately mounts the server **read-only** — model-
driven writes would duplicate what the hook already stores.

### 3. Memory you can look at

Because memories are Neo4j nodes, you can open the same workspace in Neo4j
Browser or Bloom and *see* what your agent remembers — and the agent can answer
"why did you recommend that?" by naming a real path through the graph.

### 4. Identity for free via channels

Platform channels (like Slack) attach a verified sender identity to every
message, so per-user memory works across surfaces with no extra auth code.

---

## Status

- ✅ Recall via dynamic instructions, store via hooks — no memory tool the model can forget to call
- ✅ One `MemoryClient` per user behind a single gateway; the SDK has one call site
- ✅ Reasoning steps and tool calls recorded (the "why" trail)
- ✅ Official Neo4j MCP server mounted, allow-listed to its 3 read tools
- ✅ One typed tool (`search_news`) plus a load-on-demand skill
- ✅ NAMS MCP mounted read-only, allow-listed to 5 tools
- ⬜ Bridge edges from `(:User)` to domain nodes — documented pattern, not shipped (needs a database you own)
- ✅ `eve build` bundles the driver and SDK cleanly
- ✅ Deploys to Vercel; auth verified to fail closed on the built output
- ✅ Cross-session recall covered by an eval
---

## Resources

- [eve docs](https://vercel.com/docs/eve) · [GitHub](https://github.com/vercel/eve) · [Integrations](https://vercel.com/docs/eve/install-integrations)
- [NAMS](https://memory.neo4jlabs.com) · [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) · [`@neo4j-labs/agent-memory`](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Neo4j MCP server](https://github.com/neo4j/mcp)
- Demo database: `neo4j+s://demo.neo4jlabs.com:7687` (companies/companies)

---
