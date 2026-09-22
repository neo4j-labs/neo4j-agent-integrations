# Vercel eve + Neo4j: an agent that remembers you

An AI agent that answers questions about companies from a Neo4j graph, and
remembers each user between sessions.

Close the terminal. Come back tomorrow. It still knows your name and what you
research, because none of that lived in the chat history. It lived in a graph.

**The working project is in [`industry-research-agent/`](industry-research-agent/).**

---

## The three pieces

**eve** is Vercel's framework for backend AI agents. You write your agent as
files in an `agent/` folder — instructions, tools, hooks — and eve runs them.
A file's folder decides what it does. There is no registry to update and
nothing to import.

**Neo4j** is a graph database. It stores things (a company, a person, an
article) and the links between them, instead of rows in tables. You query it
with a language called Cypher.

**NAMS** (Neo4j Agent Memory, [memory.neo4jlabs.com](https://memory.neo4jlabs.com))
is a hosted memory service built on Neo4j. You tell it what happened in a
conversation and it stores three things:

| Kind | What it holds |
|---|---|
| short-term | the conversation itself |
| long-term | facts pulled out of conversations, as a graph of entities |
| reasoning | why the agent did what it did, step by step |

Together: eve runs the agent, NAMS remembers the user, Neo4j is the database
underneath both.

---

## Why bother? A session is not memory

eve keeps a conversation alive for a long time, but that is still just one
conversation. eve's own docs say session state dies with the session, and point
you at an external store for anything that should outlive it.

eve's integration gallery has a few memory options today. All of them are
key/value or vector stores. None of them stores memory as a graph.

A graph matters here because the things worth remembering are connected. This
user follows these sectors, which contain these companies, which compete with
those companies, which appear in these articles. A flat store returns the facts
that matched your search. A graph also returns what those facts are connected
to, and can show you the path it used to find them.

---

## What you need

| | |
|---|---|
| **Node 24+** | check with `node -v` |
| **A NAMS API key** | free at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| **A model key** | `OPENAI_API_KEY`, or `AI_GATEWAY_API_KEY` for Vercel AI Gateway |
| **Neo4j** | nothing to set up — it uses a public read-only demo database |

> **Use a fresh NAMS workspace.** Long-term facts are shared by everyone in a
> workspace, so don't point this at a workspace that has other people's data in
> it.

---

## Setup

```bash
cd industry-research-agent
npm install
cp .env.example .env
```

Open `.env` and fill in two lines:

```env
NAMS_API_KEY=nams_...
OPENAI_API_KEY=sk-...
```

Everything else has a working default. The `NEO4J_*` lines already point at the
public demo graph — leave them alone.

Check it compiled:

```bash
npx eve info        # expect: 0 errors, 1 skill, 1 tool
```

---

## Run it

### Chat in your terminal

```bash
npm run chat
```

This starts the local MCP server (see below) and opens eve's chat UI. Type a
question. Ctrl+C to quit.

Try these:

```
What's been written about graph database funding?
Who are the investors in Neo4j?
What node labels does this graph have?
```

### One question at a time, no UI

```bash
npx eve invoke "Who are the investors in Neo4j?"
```

Useful in scripts and for testing. Each `invoke` is a **separate session**.

### Over HTTP

`npx eve dev` serves on `http://127.0.0.1:2000`:

```bash
curl -X POST http://127.0.0.1:2000/eve/v1/session \
  -H 'content-type: application/json' \
  -d '{"message":"Who has invested in Neo4j?"}'
# {"ok":true,"sessionId":"wrun_...","status":"accepted"}

curl -N http://127.0.0.1:2000/eve/v1/session/<sessionId>/stream
```

No auth header needed locally.

---

## See the memory work

Run these two commands one after the other:

```bash
npx eve invoke "My name is Alex and I cover the graph database sector."
npx eve invoke "What is my name and what sector do I cover?"
```

The second one knows.

That is the whole point, so it's worth being clear about why it works. Each
`eve invoke` is a separate session — the second command cannot see the first
one's chat history. No memory tool appears in either trace. The only path
between them is Neo4j: a hook stored the first exchange after it finished, and
a dynamic instruction looked it up before the second one started.

Open [memory.neo4jlabs.com](https://memory.neo4jlabs.com) to see the nodes it
made.

---

## What's in the folder

```
industry-research-agent/
├── agent/
│   ├── agent.ts                    model and reasoning effort, nothing else
│   ├── instructions.md             the system prompt
│   ├── channels/
│   │   └── eve.ts                  HTTP entry point; decides who the caller is
│   ├── connections/
│   │   ├── neo4j-graph.ts          Neo4j's hosted MCP server
│   │   ├── neo4j-investments.ts    the local MCP server in mcp-server/
│   │   └── memory-graph.ts         NAMS's MCP server, read-only
│   ├── instructions/
│   │   └── memory.ts               recall: runs before every turn
│   ├── hooks/
│   │   ├── persist-turn.ts         store: runs after every turn
│   │   └── persist-reasoning.ts    records why the agent did what it did
│   ├── tools/
│   │   └── search_news.ts          full-text search over news articles
│   ├── skills/
│   │   └── research_rules.md       query rules, loaded only when needed
│   └── lib/                        plain modules — eve does not scan this
│       ├── memory-gateway.ts       the only file that calls the NAMS SDK
│       ├── nams.ts                 config, and "whose memory is this?"
│       ├── graph-extractor.ts      turns stored text into graph entities
│       ├── model.ts                AI Gateway or direct OpenAI
│       └── neo4j.ts                MCP endpoints + the Bolt driver
├── mcp-server/                     a local MCP server you can edit
│   └── src/
│       ├── server.ts               serves the get_investments tool
│       └── neo4j.ts                the Cypher behind it
├── scripts/
│   └── chat.mjs                    npm run chat
└── evals/                          tests you run with npx eve eval
```

Folder-by-folder notes are in
[`agent/README.md`](industry-research-agent/agent/README.md).

---

## How memory works

**The runtime remembers, not the model.**

Most memory demos give the model a `save_memory` tool and hope it calls it. It
calls it for a few turns and then stops. So this project attaches memory to
events eve fires on every turn, where the model gets no say:

| File | When it runs | What it does |
|---|---|---|
| `instructions/memory.ts` | before every turn | searches NAMS with the user's message, pastes what it finds into the prompt |
| `hooks/persist-turn.ts` | after every turn | writes the exchange to NAMS |
| `hooks/persist-reasoning.ts` | after every turn | records each reasoning step and its tool calls |

All three go through one small class in `lib/memory-gateway.ts`. It is the only
file that calls the NAMS SDK, and its whole API is three methods:

```ts
const mem = memory.for(memoryScope(ctx));               // whose memory?
await mem.recall(query, 6);                             // read
await mem.remember({ content, type: "interaction" });   // write
await mem.rememberReasoning(steps);                     // the why-trail
```

Keeping the SDK behind one file means changing memory backends, adding retries,
or adding a per-tenant workspace policy is a one-file change.

Three things to know if you copy this pattern:

- **A hook that throws fails the whole turn.** Every write is wrapped in
  `try`/`catch`. If NAMS is down the user still gets their answer.
- **Recall runs per turn, not per session.** A fact stored on turn 1 is in the
  prompt by turn 2.
- **Recall searches with the user's own words.** NAMS search is keyword-based,
  so the user's nouns match stored text better than a model's paraphrase would.

### One memory client per user

`memory.for(userId)` hands back a cached client rather than building a new one.
Two reasons, both worth knowing before you refactor it away:

1. The SDK caches the user's conversation id on the client object. A fresh
   client per call means an extra network round trip before every single recall.
2. A client is locked to one NAMS workspace when it is created. Giving each
   tenant their own workspace is the only hard isolation NAMS offers today, and
   that needs one client per tenant.

The cache is bounded (`NAMS_CLIENT_CACHE`, default 250, oldest evicted first).

---

## How the agent reaches data

Four surfaces, all read-only.

| Surface | Where it comes from | Tools |
|---|---|---|
| `search_news` | `agent/tools/search_news.ts` | full-text search over articles |
| `neo4j-graph__*` | Neo4j's hosted MCP server | `get-schema`, `read-cypher`, `list-gds-procedures` |
| `neo4j-investments__*` | **the local MCP server in `mcp-server/`** | `get_investments` |
| `memory-graph__*` | NAMS's MCP server | 5 read tools for browsing its own memory |

**MCP** (Model Context Protocol) is a standard for publishing tools from a
separate server. eve's `defineMcpClientConnection` mounts one and exposes its
tools to the model as `<filename>__<tool>`, keeping URLs and credentials out of
the model's view.

Three habits worth copying from `agent/connections/`:

- **Use `tools.allow`, not `tools.block`.** NAMS's MCP server publishes over 40
  tools, including ones that delete a whole workspace. An allow-list stays safe
  when the server adds new tools. A block-list doesn't.
- **No write tools from MCP.** Storing is the hook's job. A second, optional
  path to store would bring back the coin-flip the hook exists to remove.
- **Inject `workspace_id` from the app, not the model.** Declaring it in
  `toolCall.providedArguments` makes eve hide it from the model and fill it in
  at call time. See `connections/memory-graph.ts`.

### The local MCP server

`mcp-server/` is a real MCP server with one tool, `get_investments`, backed by
one Cypher query. It is there so you can see what's on the other side of a
connection instead of only consuming servers other people run.

```bash
npm run mcp     # http://localhost:8100/mcp
```

`npm run chat` starts it for you. `agent/connections/neo4j-investments.ts` is
the agent's side of it — 20 lines, no auth, one allowed tool.

The server is optional on purpose. If nothing is listening, eve logs that the
connection published no tools and the agent answers with the other three
surfaces. That is worth seeing once:

```bash
npx eve invoke "Who are the investors in Neo4j?"    # with the server off
```

It still answers. It just writes the Cypher by hand instead.

It also speaks stdio, which is the transport desktop MCP clients use:

```bash
MCP_TRANSPORT=stdio npx tsx mcp-server/src/server.ts
```

One rule if you edit it: on stdio, **stdout is the protocol channel**. Log to
stderr or you corrupt the stream.

---

## Making changes

This is the part to read if you want to build your own version.

### Add a tool

Drop a file in `agent/tools/`. The filename becomes the tool name.

```ts
// agent/tools/company_profile.ts
import { defineTool } from "eve/tools";
import { z } from "zod";
import { readQuery } from "../lib/neo4j";

export default defineTool({
  description: "Look up one company's industry categories and city.",
  inputSchema: z.object({
    name: z.string().describe("Exact company name"),
  }),
  async execute({ name }) {
    return readQuery(
      `MATCH (o:Organization {name: $name})
       OPTIONAL MATCH (o)-[:HAS_CATEGORY]->(c:IndustryCategory)
       OPTIONAL MATCH (o)-[:IN_CITY]->(city:City)
       RETURN o.name AS name, collect(DISTINCT c.name) AS categories, city.name AS city`,
      { name },
    );
  },
});
```

Restart. The model can use it. Then add a line to `agent/instructions.md`
saying when to reach for it — a tool the prompt never mentions gets called less
often than you expect.

### Add a tool to the local MCP server instead

Do this when the tool should also be usable by something that isn't this agent
(a desktop MCP client, another team's agent).

1. Write the query in `mcp-server/src/neo4j.ts`.
2. Add an entry to the `TOOLS` array in `mcp-server/src/server.ts` and handle
   its name in the `CallToolRequestSchema` handler.
3. Add the tool name to `tools.allow` in
   `agent/connections/neo4j-investments.ts`.

Restart both. Step 3 is the one people forget — the allow-list is why a new
tool doesn't appear.

### Connect a different MCP server

One file in `agent/connections/`:

```ts
// agent/connections/linear.ts
import { defineMcpClientConnection } from "eve/connections";

export default defineMcpClientConnection({
  url: "https://mcp.linear.app/mcp",
  description: "Linear issues and projects.",   // the model reads this
  auth: { getToken: async () => ({ token: process.env.LINEAR_API_TOKEN! }) },
  tools: { allow: ["search_issues", "get_issue"] },
});
```

Write `description` for the model, not for yourself. It is the main signal eve
uses when deciding which connection to search.

### Change the model

Set `AGENT_MODEL` in `.env` to any id from
[vercel.com/ai-gateway/models](https://vercel.com/ai-gateway/models), with
`AI_GATEWAY_API_KEY` set. With only `OPENAI_API_KEY`, it talks to OpenAI
directly. `lib/model.ts` picks the route; set `MODEL_ROUTING` to force it.

### Change what gets remembered

`hooks/persist-turn.ts` decides. `isPromotable()` there filters what goes into
the long-term entity graph — it currently drops slash commands, because
extraction costs a model call and **NAMS has no delete**, so a bad entity is
awkward to unmake.

`lib/graph-extractor.ts` controls what entities come out of a stored turn. Its
prompt and its filter list are both editable.

Turn things off with env vars: `NAMS_GRAPH_MEMORY=off`, `NAMS_REASONING=off`.

### Swap the memory backend

Rewrite `lib/memory-gateway.ts` to keep the same three methods. Nothing else in
the project imports the NAMS SDK, so nothing else changes.

### Point it at your own Neo4j

Change `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`. The
queries in `tools/search_news.ts` and `mcp-server/src/neo4j.ts` assume this
dataset's schema, so rewrite those for yours.

---

## Who is the user?

For a memory agent this is the most important decision: **the verified caller
identity is the memory scope.**

`agent/channels/eve.ts` runs an ordered list of authenticators on each request
and produces `ctx.session.auth`. `memoryScope()` in `lib/nams.ts` reads the user
id from there and from nowhere else.

That matters because a tool with a `userId` parameter lets a prompt-injected
document ask for someone else's memory. An id taken from verified auth cannot be
talked into that. No tool in this project takes a `userId`.

```ts
export default eveChannel({ auth: [appSession(), vercelOidc(), localDev()] });
```

Each authenticator can accept, skip, or reject. Put your app's own first.

| Mechanism | Supported | Notes |
|---|---|---|
| API keys / bearer | yes | `httpBasic()`, `jwtHmac()`, `jwtEcdsa()`, or a custom function |
| OIDC (any issuer) | yes | `oidc({ issuer, audiences, discoveryUrl })` |
| Vercel OIDC | yes | `vercelOidc()`, zero config for Vercel-to-Vercel callers |
| OAuth 2.1 outbound | yes | `connect()` from `@vercel/connect/eve` |
| Anonymous | careful | `none()` only; otherwise it fails closed in production |

Two rules:

- **`principalId` must stay stable for the same person forever.** It becomes
  the NAMS user id. Change how you compute it and that user loses their memory.
- **Replace `placeholderAuth()` before production.** `eve init` scaffolds it and
  it rejects everyone with a 401. Leaving it in means nobody can call the agent.
  Deleting the auth walk instead means *everybody shares one memory*, which is
  worse.

Locally there is no auth, so `DEMO_USER_ID` in `.env` is the identity.

---

## Test

```bash
npx eve eval             # all of them
npx eve eval memory      # just evals/memory/
npm run typecheck
```

The one that matters is `memory/cross-session-recall`. It stores a fact, calls
`t.newSession()` to throw the transcript away, then checks the agent still knows
the fact. If that passes, the memory is real and not just a long context window.

`evals/graph/investments.eval.ts` needs the local MCP server running
(`npm run mcp` in another terminal), or it fails — correctly, because the tool
genuinely isn't there.

`npx eve eval --url https://<deployment>` runs the same files against a live
deployment, so the same tests are both your deploy gate and your production
smoke test.

---

## Deploy

```bash
npx eve link     # link or create the Vercel project
npx eve deploy
```

Set `NAMS_API_KEY`, `AGENT_MODEL`, and the `NEO4J_*` values in the Vercel
project's environment. A plain model id routes through AI Gateway using project
OIDC, so you don't need a model provider key there.

`mcp-server/` does not deploy with the agent — it's a local process. On a
deployment, either leave `INVESTMENTS_MCP_URL` unset (the agent loses that one
tool) or host the server somewhere and point at it. If you do host it, add auth:
the connection file has none, because loopback needed none.

And once more: **replace `placeholderAuth()` before real traffic.**

---

## The dataset

A public, read-only Neo4j demo database. No setup.

```env
NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687
NEO4J_USERNAME=companies
NEO4J_PASSWORD=companies
NEO4J_DATABASE=companies
```

Its schema:

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

**One trap worth knowing.** The `news` vector index was built with OpenAI's
`text-embedding-ada-002`. Query it with embeddings from a different model and
you get confident nonsense — a "graph database funding" query returned articles
about hate-speech moderation at 0.54 similarity with the wrong model, versus
the right funding articles at 0.92 with ada-002. That's why `search_news` uses
the full-text index instead: it works whatever model the agent runs on.

---

## Going further: memory and domain data in one database

Everything above keeps two databases. NAMS stores memory in its own hosted
instance, and the tools read the public news graph. That works, and it's the
right default with a hosted NAMS key.

The bigger payoff comes when memory and domain data live in the **same**
database, joined by edges. Point NAMS at a Neo4j instance you own
(`NAMS_ENDPOINT`), load your data into it, and when a user states a preference,
write an edge from their `User` node to the real domain node:

```cypher
// "I track Neo4j" → link the user to the real Organization node.
MATCH (o:Organization {name: $company})
MERGE (u:User {userId: $userId})
MERGE (u)-[t:TRACKS]->(o)
  ON CREATE SET t.since = datetime(), t.statedAs = $rawText;
```

Two details worth copying. The `User` is `MERGE`d but the domain node is only
`MATCH`ed, so a misspelled company name fails to link instead of quietly
creating a duplicate company. And `statedAs` keeps the user's own words on the
edge, so the agent can explain a recommendation in the user's language later.

Once those edges exist, "what should I read that I'm not already following?"
becomes one query instead of a search plus filtering:

```cypher
MATCH (u:User {userId: $userId})-[:FOCUSES_ON]->(cat:IndustryCategory)
MATCH (o:Organization)-[:HAS_CATEGORY]->(cat)
WHERE NOT (u)-[:TRACKS]->(o)
MATCH (a:Article)-[:MENTIONS]->(o)
RETURN o.name AS company,
       collect(DISTINCT cat.name) AS becauseYouFollow,
       collect(DISTINCT a.title)[0..3] AS headlines
ORDER BY size(headlines) DESC LIMIT 10;
```

`becauseYouFollow` is read straight off the edges that produced the row, so the
explanation can't drift from the recommendation.

**Why it isn't turned on here:** the demo database is shared and read-only, and
the hosted NAMS workspace is a different database, so no query can cross
between them. Bring your own Aura instance and both problems go away. None of
the memory wiring above changes.

---

## Known limits

Things to plan around, found while building this:

- **NAMS has no delete.** You cannot remove a single memory or entity. Filter
  before you store, not after.
- **NAMS search is lexical, not semantic.** Search with the user's own words.
- **Long-term entities carry no user id.** Isolation between users means one
  workspace per user or tenant. That's what `workspaceIdFor()` in `lib/nams.ts`
  is for.
- **Connections are static in eve 0.31.** A connection can't be mounted
  conditionally at runtime, which is why `neo4j-investments.ts` always mounts
  and simply publishes no tools when its server is down.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Answers stream but nothing is remembered | Wrong `NAMS_WORKSPACE_ID`. It 403s every memory call silently. Blank it out to use the workspace your key is bound to. |
| `get_investments` never gets called | The local MCP server isn't running. `npm run mcp`, or use `npm run chat`. |
| Every caller shares one memory | The auth walk isn't producing a user principal. Check `channels/eve.ts`. |
| `NAMS_API_KEY is not set` at startup | No `.env`, or you copied `.env.example` without filling it in. |
| Memory entries look like whole sentences as node names | The extraction model isn't resolving. Check `NAMS_EXTRACTION_MODEL` and your model credential. |

---

## Links

- eve: [docs](https://vercel.com/docs/eve) · [GitHub](https://github.com/vercel/eve) ·
  docs are also bundled at `node_modules/eve/docs/`
- NAMS: [memory.neo4jlabs.com](https://memory.neo4jlabs.com) ·
  [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) ·
  [`@neo4j-labs/agent-memory`](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Neo4j MCP server](https://github.com/neo4j/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io)
