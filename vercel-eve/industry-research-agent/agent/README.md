# `agent/` — what lives where

An eve agent **is a directory**. There is no registry and no wiring file: eve
discovers each folder by name, and a file's location is what gives it its role.
Everything below is that convention, folder by folder, then file by file.

Four systems meet in here:

```
  EVE  ──────────►  NAMS  ──────────►  Neo4j MCP  ──────────►  Neo4j
  the runtime       the memory         the graph tools         the graph
  (this folder)     (hosted)           (hosted MCP server)     (companies db)
```

| Path | Role | Pillar |
|---|---|---|
| `agent.ts` | The agent itself: model id and reasoning effort. Nothing else. | EVE |
| `instructions.md` | The always-on system prompt. | EVE |
| `instructions/` | **Dynamic** instructions — prompt text computed per event. | NAMS |
| `hooks/` | Runtime event handlers. | NAMS |
| `tools/` | Typed tools the model can call. | Neo4j |
| `connections/` | MCP servers mounted into the tool surface. | NAMS + Neo4j MCP |
| `skills/` | Markdown loaded on demand, not carried every turn. | EVE |
| `channels/` | Inbound surfaces, and where user identity comes from. | EVE |
| `lib/` | Plain modules — the only folder eve does not scan. Nothing here defines an eve primitive. | all |

**What is stored where.** The two databases behind the two right-hand pillars
never touch each other:

| Written by | Lands in | Visible at |
|---|---|---|
| `hooks/persist-turn.ts` | NAMS short-term, then long-term entities | `/dashboard/memory`, `/dashboard/entities` |
| `hooks/persist-reasoning.ts` | NAMS reasoning steps + tool calls | `/dashboard/reasoning` |
| nothing in this project | the `companies` graph — **read-only** | Neo4j Browser |

---

## Every file, in one table

The demo-facing version: 17 files under `agent/`, what each one does, and the
one sentence to say about it out loud.

| File | Does | The line to say |
|---|---|---|
| `agent.ts` | Model id + reasoning effort | "Memory isn't configured here. That's the point." |
| `instructions.md` | Always-on system prompt: identity, 5 tools, how to research and report | "The tool surface, described once." |
| `instructions/memory.ts` | **Recall.** `turn.started` → NAMS search → prompt block | "Memory arrives as prompt *data*, not as a tool result." |
| `hooks/persist-turn.ts` | **Retention.** Buffers the exchange, writes short-term + long-term on `turn.completed` | "The runtime says a turn happened, so it gets stored. The model has no say." |
| `hooks/persist-reasoning.ts` | **Provenance.** Buffers reasoning blocks + tool calls, writes on `turn.completed` | "This is what makes *'why did you say that?'* answerable." |
| `tools/search_news.ts` | Full-text search over article chunks, via Bolt | "The only authored tool, and the only thing MCP couldn't cover." |
| `connections/neo4j-graph.ts` | Official Neo4j MCP server, 3 read tools | "Schema and Cypher are the server's job, not code we maintain." |
| `connections/memory-graph.ts` | NAMS MCP server, 5 read tools of 40 | "The agent can traverse its own memory — but only read it." |
| `skills/research_rules.md` | Load-on-demand querying + citation procedure | "Not in the prompt until the model needs it." |
| `channels/eve.ts` | HTTP surface; the auth walk that yields identity | "This is the memory boundary. Nothing downstream re-decides who you are." |
| `channels/slack.ts` | Mentions and DMs; identity from the Slack sender | "Zero memory code in here, and two Slack users get two namespaces." |
| `lib/memory-gateway.ts` | **The only file that calls the NAMS SDK.** One `MemoryClient` per user, LRU-bounded | "One door to memory. Swapping the backend is a one-file change." |
| `lib/nams.ts` | Config, env flags, shared types, prompt rendering, and `memoryScope` | "`memoryScope` reads verified session auth and nothing else." |
| `lib/graph-extractor.ts` | Stored memory → entities and edges; filters the agent's own machinery out | "A prompt can't hold a boundary that has no undo behind it. A filter can." |
| `lib/neo4j.ts` | Both routes to the graph: MCP headers/allow-list, and the Bolt `readQuery` | "No write path exists in this file, on either route." |
| `lib/model.ts` | AI Gateway or a direct provider; the extraction model | "One switch, so the demo runs with or without a Vercel account." |
| `README.md` | This file | — |

---

## `agent.ts` — the agent

Model and reasoning effort, and deliberately nothing else. Memory is not
configured here because it is not a model setting: it is a hook on the turn
(`hooks/`) and a dynamic instruction (`instructions/`).

A plain model id string is preferred over a resolved model object, because that
is what lets eve compile build-time routing, credential, and context-window
metadata. The one exception is the direct-provider route (`MODEL_ROUTING=openai`),
which has to hand `defineAgent` a resolved `LanguageModelV4`.

**Why not memory-in-the-model.** `@neo4j-labs/nams-ai-provider` offers exactly
that — `createNamsProvider` / `createNams().wrap()` — and this project ran on it
before reverting. Wrapping the model stores every turn with no say in what is
worth keeping, hides its own write failures inside the wrapper, and records no
reasoning memory at all.

## `instructions.md` + `instructions/` — the prompt, static and dynamic

`instructions.md` is always on: identity, the tool surface, how to research, how
to report, and the rule that recalled memory is *data about the user*, never an
instruction that can override the prompt.

`instructions/memory.ts` is the **recall half**. It resolves on `turn.started` —
not `session.started` — so a fact stored on turn 1 is in the prompt by turn 2 of
the same session. It queries NAMS with what the user *just said*, because NAMS
search is lexical: the user's own nouns match stored text better than a
paraphrase would. Returns `null` on failure, so a NAMS outage costs memory, not
the turn.

`renderMemories` in `lib/nams.ts` is what wraps the hits, and the wrapper text
matters: it labels the block as user-provided facts and tells the model not to
treat it as instructions. Recalled text is untrusted input.

## `hooks/` — the retention half

| File | Writes | NAMS memory type | Events |
|---|---|---|---|
| `persist-turn.ts` | the exchange, then promotes it to entities | short-term, then long-term | `message.received`, `message.completed` → `turn.completed` |
| `persist-reasoning.ts` | one step per reasoning block, tool calls hanging off each | reasoning | `actions.requested`, `action.result`, `reasoning.completed` → `turn.completed` |

**The point of this folder:** the runtime tells the agent a turn happened, so
retention never depends on the model choosing to call a save tool. There is no
`remember` tool in this project, and forgetting is not a failure mode the model
can cause.

Both buffer during the turn in `defineState` and flush on `turn.completed`,
which keeps writes off the streaming path. State, not a module-level variable:
the two halves of an exchange arrive in different events, which means different
steps, and a step can resume on another machine.

`persist-reasoning` *has* to buffer: a step's tool calls are only known after its
`reasoning.completed` fires, and `recordToolCall` needs the id of the step it
belongs to. It pairs each step's reasoning block with the tool calls made at the
same `stepIndex`, then writes them oldest-step-first.

`persist-turn` stores twice, with separate `catch`es. `storeMemory` returns
early on `interaction` and never touches `longTerm`, so the second call is the
only thing that moves the entity graph — and its failure must not cost the
transcript. It also drops slash commands before spending an extraction call:
`/channels` is what once put `analysis` and `final` into the workspace as
`Concept` entities, and NAMS has no entity delete.

Both wrap every store in `try`/`catch`, because **a thrown hook fails the turn**
and memory is an enhancement, not a dependency of the answer the user already
received.

## `tools/` — typed tools

One file, one tool, named by its filename.

- `search_news.ts` — full-text search over article chunks, via the Bolt driver.
  Returns titles, dates, publisher, sentiment, and the matching passage, plus
  the organizations each article mentions.

It is the only authored tool, and it exists because it queries the
`news_fulltext` index — the one thing the MCP server below publishes no tool
for. Everything else that needs the graph goes through `connections/`.

**There is no memory tool, on purpose.** Memory is written by `hooks/` on the
runtime's schedule. A `remember` tool is the only shape where forgetting to call
it means forgetting the user.

**No tool takes a `userId`.** That is recipe rule 3, and it is enforced by
absence: identity comes from `memoryScope(ctx)`, so the model has no argument it
could use to address another user's memory.

## `connections/` — MCP servers

`defineMcpClientConnection` points eve at any Streamable-HTTP or SSE MCP server
and exposes its tools as `<filename>__<tool>`. Both connections here are
read-only and both use an explicit `tools.allow` list.

| File | Server | Auth | Tools exposed |
|---|---|---|---|
| `neo4j-graph.ts` | official Neo4j MCP server | HTTP **Basic**, via `headers` | `get-schema`, `read-cypher`, `list-gds-procedures` |
| `memory-graph.ts` | NAMS's MCP server | **Bearer**, via `auth.getToken` | 5 read tools, out of the 40 it publishes |

The allow-lists are not decoration. NAMS's 40 tools include nine writes and
thirteen `skill_*` tools that can generate, edit, and publish the agent's own
skills; the Neo4j server's `read-cypher` description points at a `write-cypher`
sibling. Naming the tools you want is the only thing that keeps the rest away
from the model.

The two auth shapes differ for a reason worth knowing: eve's `auth.getToken`
always sends `Authorization: Bearer <token>`, and the Neo4j MCP server answers
an unauthenticated request with `WWW-Authenticate: Basic`. So its credentials go
through the `headers` callback instead — which is re-resolved per request, so
rotating the env vars needs no redeploy.

`memory-graph.ts` also injects `workspace_id` through `providedArguments` when
`NAMS_WORKSPACE_ID` is set, resolved from `ctx` — the same identity seam as
everything else, so the model never supplies it.

## `skills/` — loaded on demand

`research_rules.md` holds the order of resort across the tools, the exact-name
retry, the citation rules, and the "memory is context, not evidence" rule. It
carries a `description` in frontmatter that tells the model when to load it, and
it is **not** in the prompt until it does. The reason it is a skill and not a
paragraph in `instructions.md` is cost: it is a procedure needed on research
turns and dead weight on every other turn.

## `channels/` — inbound surfaces and identity

| File | Surface | Identity |
|---|---|---|
| `eve.ts` | HTTP (`POST /eve/v1/session`) | `vercelOidc()` → `localDev()` → `placeholderAuth()` |
| `slack.ts` | mentions and DMs | the Slack sender on the inbound event |

**Why this folder matters to memory:** the authenticated caller *is* the memory
boundary. `memoryScope` in `lib/nams.ts` reads it from verified session context
and nothing else, so two Slack users get two memory namespaces without either
channel knowing NAMS exists.

The `eve.ts` walk is ordered and fail-closed. `vercelOidc()` yields a
`principalType: "user"` principal when the token carries an `external_sub`;
`localDev()` yields a `local-dev` principal, which `memoryScope` deliberately
does *not* accept as a user — that is what makes `DEMO_USER_ID` the demo
identity; and `placeholderAuth()` throws a structured 401 in production, so an
unfinished deployment refuses traffic rather than silently sharing one namespace.
**Replace it with your app's authenticator before serving real users** — that is
recipe rule 3 in one file.

`slack.ts` needs no auth entry: the channel HMAC-verifies the inbound webhook
and builds the principal itself, `slack:<team>:<user>`, typed `"user"` for a
human sender and `"service"` for a bot. The channel file contains no memory code
at all, which is the demonstration.

## `lib/` — plain modules

Nothing here defines an eve primitive, so eve does not scan it. This is where
the integrations actually live. **Five files.** `memoryScope` sits in `nams.ts`
because every caller that needs one needs the other, and both routes to the
graph sit in `neo4j.ts` because they are one decision.

| File | Holds |
|---|---|
| `memory-gateway.ts` | **the only file that calls the NAMS SDK.** One `MemoryClient` per user, LRU-bounded |
| `nams.ts` | config, env flags, shared types, prompt rendering, and `memoryScope` — the memory boundary |
| `graph-extractor.ts` | a stored memory → entities; its own prompt, and the filter that keeps the agent's machinery out |
| `neo4j.ts` | **both routes to the graph**: the MCP endpoint and allow-list, and the Bolt driver's `readQuery`. No write path on either |
| `model.ts` | AI Gateway or a direct provider, plus the extraction model |

**Why a gateway.** Hooks, tools, and dynamic instructions all reach memory
through `memory.for(scope)` and never import the NAMS SDK themselves. Retries,
timeouts, a workspace-per-tenant policy, or a different memory backend entirely
are one-file changes — and a bug like the provider's permanently cached
conversation id is one this project can actually fix, because the client
lifetime is ours.

**Why one client per user.** `resolveConversation` caches the conversation id on
the client *instance*, so a fresh client per call means a wasted
`list_conversations` round trip before every recall and every store. The map key
is the userId namespace, and the map is bounded (`NAMS_CLIENT_CACHE`, default
256, LRU).

**What the gateway exposes** is three verbs and nothing else — `recall`,
`remember`, `rememberReasoning`. `rememberReasoning` uses
`findExistingConversation`, never `resolveConversation`: a trace is provenance
for a conversation that already happened, so it must never be the thing that
creates one.

**`graph-extractor.ts` is the reason the entity graph is worth looking at.**
Without an extractor, `storeMemory` falls back to one flat node whose *name is
the first 60 characters of the turn* — a graph made of sentences. With one, a
turn becomes named entities and the edges between them. It replaces the
provider's default for two reasons that outlived the schema bug that first
forced it: its prompt is told to *include* the analyst's own identity and
coverage areas, and its filter does not drop all-lowercase names, because
"undersea cable operators" is exactly what this agent should remember. The
`NOT_DOMAIN_ENTITIES` filter runs after the model answers, because NAMS has no
entity delete and a prompt cannot be relied on to hold a boundary with no undo
behind it.

---

## The two routes to Neo4j

Both reach the same `companies` database, and the split is deliberate:

```
  tools/search_news.ts ───────► lib/neo4j.ts ──────► bolt ──────┐
                                                                ├──► companies db
  connections/neo4j-graph.ts ──► lib/neo4j.ts ──────► https (MCP) ┘
```

MCP is the default — schema and Cypher are the server's job, not code to
maintain. The driver stays for `search_news` alone, because a full-text index
query has no MCP tool behind it. `readQuery` pins `routing: "READ"` at the
driver rather than trusting the query text, and narrows Neo4j integers to JS
numbers so results survive eve's durable JSON boundary.

---

## Outside `agent/`

Paths are relative to this file.

| Path | What it is |
|---|---|
| [`../evals/evals.config.ts`](../evals/evals.config.ts) | judge model + timeout for `eve eval` |
| [`../evals/memory/cross-session-recall.eval.ts`](../evals/memory/cross-session-recall.eval.ts) | **the load-bearing test.** `t.newSession()` discards the transcript, so anything recalled afterwards came out of NAMS |
| [`../evals/graph/news-search.eval.ts`](../evals/graph/news-search.eval.ts) | asserts a company question reaches `search_news` rather than model recall |
| [`../.env.example`](../.env.example) | every knob, annotated — copy to `.env` |
| [`../package.json`](../package.json) | `dev` / `build` / `deploy` / `eval` / `typecheck`; pins `ai@^7` across the tree via `overrides` |
| [`../../README.md`](../../README.md) | the integration reference: extension points, the 9 documented NAMS gaps, co-locating memory and domain data |

## The recipe, mapped to files

| Rule | Where it lives | State |
|---|---|---|
| 1. Wrap the SDK behind a `MemoryGateway`, one client per user | `lib/memory-gateway.ts` | ✅ shipped |
| 2. Persist in a hook, not a tool | `hooks/persist-turn.ts`, `hooks/persist-reasoning.ts` | ✅ shipped |
| 3. Bind identity in the channel; no `userId` in any tool input | `channels/`, `lib/nams.ts` → `memoryScope` | ✅ shipped; `channels/eve.ts` still carries the scaffold `placeholderAuth()` — replace it for production |
| 4. Point NAMS at your own Neo4j and write bridge edges | — | ⬜ **not shipped.** Needs a database you own; the demo graph is read-only. Pattern in [`README.md` → Co-locating memory and domain data](../../README.md#co-locating-memory-and-domain-data) |
