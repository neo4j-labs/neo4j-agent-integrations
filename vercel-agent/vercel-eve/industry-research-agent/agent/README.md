# `agent/` — what lives where

An eve agent **is a directory**. There is no wiring file: eve looks for folders
by name, and where a file sits is what decides its job. Move
`tools/search_news.ts` into `lib/` and it stops being a tool.

This file walks the folders. Start here if you're about to change something.

| Folder | What eve does with it |
|---|---|
| `agent.ts` | The agent itself: model, reasoning effort, and eve's default tools switched off. |
| `instructions.md` | The system prompt, always on. |
| `memory/` | Memory slots. One file, one slot, backed by a provider. |
| `tools/` | Typed tools the model can call. One file, one tool. |
| `connections/` | MCP servers mounted into the tool surface. |
| `skills/` | Markdown loaded on demand, not carried every turn. |
| `channels/` | How users reach the agent, and who they are. |
| `lib/` | Plain modules. **The only folder eve does not scan.** |

---

## The files

| File | What it does |
|---|---|
| `agent.ts` | Model id + reasoning effort; `defaultTools: false`. Memory is deliberately not here. |
| `instructions.md` | Identity, the research tools, memory, how to research, how to report. |
| `memory/nams.ts` | **All of the agent's memory.** The NAMS slot from `@neo4j-labs/nams-ai-provider/eve`, wrapped so it also saves reasoning steps. |
| `tools/search_news.ts` | Full-text search over article text, over Bolt. |
| `connections/neo4j-graph.ts` | Neo4j's hosted MCP server, 3 read tools. |
| `connections/neo4j-investments.ts` | The local MCP server in `../mcp-server/`, 1 tool. |
| `skills/research_rules.md` | Query and citation rules, loaded when needed. |
| `channels/eve.ts` | The HTTP surface, and the auth walk that yields identity. |
| `lib/model.ts` | AI Gateway or direct OpenAI. |
| `lib/neo4j.ts` | Both routes to the graph: MCP endpoints, and the Bolt driver. |
| `lib/nams-reasoning.ts` | Wraps the memory provider so each turn's reasoning steps and tool calls are saved to NAMS. |

---

## `agent.ts`

Model, reasoning effort, and `defaultTools: false`. Memory isn't configured
here because it isn't a model setting — it's a slot in `memory/`.

`defaultTools: false` removes the tools eve gives every agent by default
(`bash`, `read_file`, `write_file`, `web_fetch`, `web_search`, `agent`), so the
model can only use the research tools and memory that `instructions.md`
describes. Left on, `web_search` answers "what's new" questions from the live
web instead of the graph. eve's catalog tools (`eve__search`, `eve__skill`) stay,
because they are how the model finds the MCP tools and loads the skill.

A plain model id string is preferred over a resolved model object, because a
string is what lets eve work out routing, credentials, and context window at
build time. The exception is `MODEL_ROUTING=openai`, which has to hand
`defineAgent` a real model instance.

## `instructions.md`

Always in the prompt: identity, the research tools, the two memory tools, how
to research, how to report, and the rule that recalled memory is *data about
the user* and never an instruction.

## `memory/` — the only memory

`memory/nams.ts` is one eve memory slot, named `nams` after its file. It is the
**only** place the agent reads or writes memory: no hooks, no dynamic
instructions, and no memory MCP server. The one NAMS call outside the package is
`lib/nams-reasoning.ts`, which the slot wraps around the provider.

```ts
import { namsMemory } from "@neo4j-labs/nams-ai-provider/eve";
import { defineMemory } from "eve/memory";
import { byPrincipal } from "eve/memory/scope";
import { withReasoningTrace } from "../lib/nams-reasoning";

export default defineMemory({
  description: "What this user told you in earlier sessions…",
  provider: withReasoningTrace(
    namsMemory({ apiKey: process.env.NAMS_API_KEY, /* … */ }),
    { apiKey: process.env.NAMS_API_KEY, /* … */ },
  ),
  scope: byPrincipal,
});
```

eve drives the slot through its own lifecycle, and the provider does the NAMS
work:

| When | What happens |
|---|---|
| Before each turn (and after compaction) | **Recall.** One memory message: notes saved with `remember`, the summaries NAMS wrote about this user's earlier sessions, earlier messages that match what the user just said, and matching entities from this user's knowledge graph. It enters the prompt as a user-role message attributed to the slot, never as system instructions. |
| After each turn | **Capture.** The user's message and the final answer go to one NAMS conversation per eve session. NAMS extracts entities and writes summaries (observations, reflections) from it server-side, on its own schedule. |
| After each turn, after capture | **Reasoning trace.** `withReasoningTrace` saves one reasoning step per model call to the same conversation: the model's reasoning summary (or its narration), the tools it called, and what they returned, with each tool call attached to its step. The final answer is a `direct response` step. This is what the NAMS dashboard's reasoning view shows. |
| During the turn | **Tools.** `nams__search` searches earlier sessions, notes and this user's entities; `nams__remember` saves a note. Both are bound to the current user. |

**Who the memory belongs to.** `scope: byPrincipal` keys memory to the
authenticated caller from `ctx.session.auth.current`. eve turns that into an
opaque `memory.scope.key`, and the provider writes it as the NAMS `userId` of
every conversation. The raw principal id never reaches NAMS. Anonymous and
runtime callers get no memory at all, and every `eve dev` caller shares one
`local-dev` scope.

**Isolation on hosted NAMS.** The provider asks NAMS for this user's
conversations and entities only, and also checks the `userId` on each one that
comes back. Entities that belong to no user (shared across the workspace) are
left out of recall by the provider's `workspaceGraph: false` default.

**Replays and failures.** A replayed recall returns the same record and a
replayed capture writes nothing twice. A missing or rejected API key fails the
turn; any other NAMS error during recall is logged and the turn continues with
a record that says memory is unavailable.

Settings come from `.env`: `NAMS_API_KEY` (required), `WORKSPACE_ID`,
`NAMS_ENDPOINT`, `NAMS_MAX_MEMORIES` (default 8), and `NAMS_REASONING`
(`off` stops saving reasoning steps).

## `tools/` — typed tools

One file, one tool, named by its filename.

`search_news.ts` is the only one. It queries the `news_fulltext` index, which
is the one thing the Neo4j MCP server publishes no tool for. Everything else
that needs the graph goes through `connections/`.

Memory tools are not here: `nams__search` and `nams__remember` come from the
memory slot. Saving doesn't depend on them — capture runs after every turn
whether or not the model calls `remember`.

**No tool takes a `userId`.** The memory tools are bound to the slot's locked
scope, so the model has no argument it could use to reach another user's
memory.

## `connections/` — MCP servers

`defineMcpClientConnection` points eve at any MCP server and exposes its tools
as `<filename>__<tool>`. Both here are read-only with an explicit
`tools.allow` list.

| File | Server | Auth | Tools |
|---|---|---|---|
| `neo4j-graph.ts` | Neo4j's hosted MCP server | Basic, via `headers` | `get-schema`, `read-cypher`, `list-gds-procedures` |
| `neo4j-investments.ts` | `../mcp-server/`, on localhost | none — loopback only | `get_investments` |

**Why `headers` and not `auth`.** eve's `auth.getToken` always sends
`Authorization: Bearer <token>`, and the Neo4j MCP server answers an
unauthenticated request with `WWW-Authenticate: Basic`. So its credentials go
through the `headers` callback instead — which is re-resolved per request, so
rotating the env vars needs no redeploy.

`neo4j-investments.ts` is the one pointing at a server you run yourself, and
the one to copy when adding your own. It has no auth because it only listens on
loopback — add `auth` or `headers` the moment it's reachable from anywhere else.

`neo4j-investments.ts` always mounts. When its server is down, eve logs that
the connection published no tools and the agent runs with the other surfaces.

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
boundary. The slot's `byPrincipal` scope reads it from verified session context
and nothing else.

Walking the three in order:

- `vercelOidc()` yields a principal from the Vercel OIDC token, so each caller
  gets their own memory.
- `localDev()` yields a `local-dev` principal, which `byPrincipal` maps to one
  shared `local-dev` scope: everything you do under `eve dev` is one user.
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
| `neo4j.ts` | both routes to the graph, plus the local MCP url. No write path on any |
| `model.ts` | AI Gateway or a direct provider |
| `nams-reasoning.ts` | `withReasoningTrace()`: after the provider captures a turn, finds that session's NAMS conversation and records the turn's reasoning steps and tool calls on it |

`nams-reasoning.ts` is the only file in `lib/` that touches memory.

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
| [`../scripts/ontology.ts`](../scripts/ontology.ts) | `npm run ontology` — activates the industry-research ontology on the NAMS workspace, so extracted entities are typed `Company`, `Person`, `FundingRound`, `Sector` |
| [`../evals/memory/cross-session-recall.eval.ts`](../evals/memory/cross-session-recall.eval.ts) | **the load-bearing test.** Each `t.send()` starts a new session, so what the second one recalls came from the NAMS slot |
| [`../evals/graph/news-search.eval.ts`](../evals/graph/news-search.eval.ts) | a company question reaches `search_news`, not model recall |
| [`../evals/graph/investments.eval.ts`](../evals/graph/investments.eval.ts) | the local MCP tool gets used. Needs `npm run mcp` running |
| [`../.env.example`](../.env.example) | every setting, annotated. Copy to `.env` |
| [`../../README.md`](../../README.md) | setup, how to change things, deployment, known limits |
