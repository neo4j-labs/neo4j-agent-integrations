# `agent/` — what lives where

An eve agent **is a directory**. There is no wiring file: eve looks for folders
by name, and where a file sits is what decides its job. Move
`tools/search_news.ts` into `lib/` and it stops being a tool.

This file walks the folders. Start here if you're about to change something.

| Folder | What eve does with it |
|---|---|
| `agent.ts` | The agent itself: model and reasoning effort. |
| `instructions.md` | The system prompt, always on. |
| `instructions/` | Prompt text computed per event, at runtime. |
| `hooks/` | Handlers for runtime events like "a turn finished". |
| `tools/` | Typed tools the model can call. One file, one tool. |
| `connections/` | MCP servers mounted into the tool surface. |
| `skills/` | Markdown loaded on demand, not carried every turn. |
| `channels/` | How users reach the agent, and who they are. |
| `lib/` | Plain modules. **The only folder eve does not scan.** |

---

## The files

| File | What it does |
|---|---|
| `agent.ts` | Model id + reasoning effort. Memory is deliberately not here. |
| `instructions.md` | Identity, the six tools, how to research, how to report. |
| `instructions/memory.ts` | **Recall.** Searches NAMS before each turn, adds a prompt block. |
| `hooks/persist-turn.ts` | **Store.** Writes the exchange after each turn. |
| `hooks/persist-reasoning.ts` | **Why-trail.** Records reasoning steps and tool calls. |
| `tools/search_news.ts` | Full-text search over article text, over Bolt. |
| `connections/neo4j-graph.ts` | Neo4j's hosted MCP server, 3 read tools. |
| `connections/neo4j-investments.ts` | The local MCP server in `../mcp-server/`, 1 tool. |
| `connections/memory-graph.ts` | NAMS's MCP server, 5 read tools out of 40. |
| `skills/research_rules.md` | Query and citation rules, loaded when needed. |
| `channels/eve.ts` | The HTTP surface, and the auth walk that yields identity. |
| `lib/memory-gateway.ts` | The only file that calls the NAMS SDK. |
| `lib/nams.ts` | Config, env flags, shared types, and `memoryScope`. |
| `lib/graph-extractor.ts` | Turns a stored memory into entities and edges. |
| `lib/model.ts` | AI Gateway or direct OpenAI; the extraction model. |
| `lib/neo4j.ts` | Both routes to the graph: MCP endpoints, and the Bolt driver. |

---

## `agent.ts`

Model and reasoning effort, and nothing else. Memory isn't configured here
because it isn't a model setting — it's a hook on the turn and a dynamic
instruction.

A plain model id string is preferred over a resolved model object, because a
string is what lets eve work out routing, credentials, and context window at
build time. The exception is `MODEL_ROUTING=openai`, which has to hand
`defineAgent` a real model instance.

**Why not memory inside the model?** `@neo4j-labs/nams-ai-provider` can wrap any
model so memory happens invisibly on every call. This project ran on that and
went back to hooks. Wrapping the model stores every turn with no filtering,
hides its own write failures inside the wrapper, and records no reasoning
memory at all.

## `instructions.md` and `instructions/`

`instructions.md` is always in the prompt: identity, the tool surface, how to
research, how to report, and the rule that recalled memory is *data about the
user* and never an instruction.

`instructions/memory.ts` is the **recall half**. Two decisions in it are worth
copying:

- It runs on `turn.started`, not `session.started`, so a fact stored on turn 1
  is in the prompt by turn 2 of the same session.
- It searches with what the user *just said*. NAMS search is keyword-based, so
  the user's own nouns match stored text better than a paraphrase would.

It returns `null` on failure, so a NAMS outage costs you memory, not the turn.

`renderMemories()` in `lib/nams.ts` wraps the results, and its wording matters:
it labels the block as user-provided facts and tells the model not to treat it
as instructions. Recalled text is untrusted input.

## `hooks/` — the store half

| File | Writes | Listens to |
|---|---|---|
| `persist-turn.ts` | the exchange, then promotes it to entities | `message.received`, `message.completed` → `turn.completed` |
| `persist-reasoning.ts` | one record per reasoning step, with its tool calls | `actions.requested`, `action.result`, `reasoning.completed` → `turn.completed` |

**The point of this folder:** the runtime says a turn happened, so it gets
stored. There is no `remember` tool, and forgetting isn't a failure mode the
model can cause.

Both buffer during the turn in `defineState` and flush on `turn.completed`, so
writes stay off the streaming path. It has to be `defineState` rather than a
module-level variable, because the two halves of an exchange arrive in
different events — which means different steps, and a step can resume on
another machine.

`persist-reasoning` has to buffer for a second reason: a step's tool calls are
only known once its `reasoning.completed` has fired, and `recordToolCall` needs
the id of the step it belongs to.

`persist-turn` stores twice, with separate `catch` blocks. `storeMemory`
returns early on `interaction` and never touches long-term, so the second call
is the only thing that moves the entity graph — and its failure must not cost
you the transcript from the first.

It also drops slash commands before spending an extraction call. `/channels` is
what once put `analysis` and `final` into the workspace as `Concept` entities,
and **NAMS has no entity delete**.

Every store is wrapped in `try`/`catch`, because **a hook that throws fails the
turn** and memory is an enhancement, not a dependency of an answer the user has
already received.

## `tools/` — typed tools

One file, one tool, named by its filename.

`search_news.ts` is the only one. It queries the `news_fulltext` index, which
is the one thing the Neo4j MCP server publishes no tool for. Everything else
that needs the graph goes through `connections/`.

**There is no memory tool, on purpose.** A `remember` tool is the only shape
where the model forgetting to call it means forgetting the user.

**No tool takes a `userId`.** Identity comes from `memoryScope(ctx)`, so the
model has no argument it could use to reach another user's memory. That's
enforced by absence, which is the only way it stays enforced.

## `connections/` — MCP servers

`defineMcpClientConnection` points eve at any MCP server and exposes its tools
as `<filename>__<tool>`. All three here are read-only with an explicit
`tools.allow` list.

| File | Server | Auth | Tools |
|---|---|---|---|
| `neo4j-graph.ts` | Neo4j's hosted MCP server | Basic, via `headers` | `get-schema`, `read-cypher`, `list-gds-procedures` |
| `neo4j-investments.ts` | `../mcp-server/`, on localhost | none — loopback only | `get_investments` |
| `memory-graph.ts` | NAMS's MCP server | Bearer, via `auth.getToken` | 5 read tools of 40 |

The allow-lists are not decoration. NAMS's 40 tools include nine writes and
thirteen `skill_*` tools that can generate, edit, and publish the agent's own
skills. Naming the tools you want is the only thing keeping the rest away from
the model.

**The two auth shapes differ for a reason.** eve's `auth.getToken` always sends
`Authorization: Bearer <token>`, and the Neo4j MCP server answers an
unauthenticated request with `WWW-Authenticate: Basic`. So its credentials go
through the `headers` callback instead — which is re-resolved per request, so
rotating the env vars needs no redeploy.

`memory-graph.ts` also injects `workspace_id` through `providedArguments` when
`NAMS_WORKSPACE_ID` is set, resolved from `ctx`. Same identity seam as
everything else: the model never supplies it.

`neo4j-investments.ts` is the one pointing at a server you run yourself, and
the one to copy when adding your own. It has no auth because it only listens on
loopback — add `auth` or `headers` the moment it's reachable from anywhere else.

**Connections are static in eve 0.31.** There is no way to mount one
conditionally at runtime, so `neo4j-investments.ts` always mounts. When its
server is down, eve logs that the connection published no tools and the agent
runs with the other three surfaces.

## `skills/` — loaded on demand

`research_rules.md` holds the order of resort across the tools, the exact-name
retry, and the citation rules. Its frontmatter `description` tells the model
when to load it, and it is **not** in the prompt until it does.

It's a skill rather than a paragraph in `instructions.md` for one reason: it's
a procedure needed on research turns and dead weight on every other turn.

## `channels/` — how users arrive, and who they are

`eve.ts` is the HTTP surface (`POST /eve/v1/session`). Its auth walk is
`vercelOidc()` → `localDev()` → `placeholderAuth()`, ordered and fail-closed.

**Why this folder matters to memory:** the authenticated caller *is* the memory
boundary. `memoryScope()` in `lib/nams.ts` reads it from verified session
context and nothing else.

Walking the three in order:

- `vercelOidc()` yields a `principalType: "user"` principal when the token
  carries an `external_sub`.
- `localDev()` yields a `local-dev` principal, which `memoryScope` deliberately
  does **not** accept as a user. That's what makes `DEMO_USER_ID` the local
  identity.
- `placeholderAuth()` throws a structured 401 in production, so an unfinished
  deployment refuses traffic rather than quietly sharing one namespace.
  **Replace it with your app's authenticator before serving real users.**

Adding a platform channel (Slack, say) is where this pays off: the channel
HMAC-verifies the webhook and builds the principal itself, so two Slack users
get two memory namespaces with no memory code in the channel file at all.

## `lib/` — plain modules

Nothing here defines an eve primitive, so eve doesn't scan it. This is where the
integrations actually live.

| File | Holds |
|---|---|
| `memory-gateway.ts` | the only file that calls the NAMS SDK; one client per user, LRU-bounded |
| `nams.ts` | config, env flags, shared types, prompt rendering, and `memoryScope` |
| `graph-extractor.ts` | a stored memory → entities; its own prompt and filter |
| `neo4j.ts` | both routes to the graph, plus the local MCP url. No write path on any |
| `model.ts` | AI Gateway or a direct provider, plus the extraction model |

**Why a gateway.** Hooks, tools, and dynamic instructions all reach memory
through `memory.for(scope)` and never import the SDK themselves. So retries,
timeouts, a workspace-per-tenant policy, or a different backend entirely are
one-file changes.

**Why one client per user.** `resolveConversation` caches the conversation id on
the client *instance*. A fresh client per call means a wasted
`list_conversations` round trip before every recall and every store. The map key
is the user id namespace, and the map is bounded (`NAMS_CLIENT_CACHE`, default
250, oldest evicted first).

**The gateway exposes three verbs and nothing else** — `recall`, `remember`,
`rememberReasoning`. `rememberReasoning` uses `findExistingConversation` and
never `resolveConversation`, because a trace is provenance for a conversation
that already happened. It must never be the thing that creates one.

**`graph-extractor.ts` is why the entity graph is worth looking at.** Without an
extractor, `storeMemory` falls back to one flat node whose *name is the first 60
characters of the turn* — a graph made of sentences, which is worse than no
graph. With one, a turn becomes named entities and the edges between them.

It replaces the provider's default for two reasons: its prompt is told to
*include* the analyst's own identity and coverage areas, and its filter doesn't
drop all-lowercase names, because "undersea cable operators" is exactly the kind
of thing this agent should remember. The `NOT_DOMAIN_ENTITIES` filter runs after
the model answers, because NAMS has no entity delete and a prompt can't hold a
boundary that has no undo behind it.

---

## The routes to Neo4j

Three ways into the same `companies` database:

```
  tools/search_news.ts ──────────► lib/neo4j.ts ──► bolt ─────────┐
                                                                  │
  connections/neo4j-graph.ts ────► lib/neo4j.ts ──► https (MCP) ───┼──► companies db
                                                                  │
  connections/neo4j-investments ─► ../mcp-server/ ─► bolt ─────────┘
                                   (separate process)
```

MCP is the default — schema and Cypher are the server's job, not code to
maintain. The driver stays for `search_news` alone, because a full-text index
query has no MCP tool behind it. The local server is a third route on purpose:
it's the one you can open up and edit.

`readQuery` pins `routing: "READ"` at the driver rather than trusting the query
text, and narrows Neo4j integers to JS numbers so results survive eve's durable
JSON boundary.

---

## Outside `agent/`

Paths relative to this file.

| Path | What it is |
|---|---|
| [`../mcp-server/`](../mcp-server/) | a local MCP server, one tool, editable |
| [`../scripts/chat.mjs`](../scripts/chat.mjs) | `npm run chat` — starts the MCP server, then eve's chat UI |
| [`../evals/memory/cross-session-recall.eval.ts`](../evals/memory/cross-session-recall.eval.ts) | **the load-bearing test.** `t.newSession()` discards the transcript, so anything recalled afterwards came from NAMS |
| [`../evals/graph/news-search.eval.ts`](../evals/graph/news-search.eval.ts) | a company question reaches `search_news`, not model recall |
| [`../evals/graph/investments.eval.ts`](../evals/graph/investments.eval.ts) | the local MCP tool gets used. Needs `npm run mcp` running |
| [`../.env.example`](../.env.example) | every setting, annotated. Copy to `.env` |
| [`../../README.md`](../../README.md) | setup, how to change things, deployment, known limits |
