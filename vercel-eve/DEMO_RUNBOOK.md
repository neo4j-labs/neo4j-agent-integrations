# Demo runbook — eve + NAMS + Neo4j, end to end

What to type, what to ask, and what to say. [`PITCH_AND_DEMO.md`](PITCH_AND_DEMO.md)
is the argument; this is the operations manual for putting it on a screen.

**Total prep:** 20 minutes. **Runtime:** ~6 minutes.

Every graph question below was run against the live demo instance and the
expected answers are real. The memory behaviour is described from the code, not
from a recorded run — do the dry run in step 4, because a memory demo that has
never been rehearsed is a memory demo that fails in front of people.

---

## 1. What you are demonstrating

Three layers, one sentence each. Say this once, at the top, and never again:

| Layer | Role in the demo |
|---|---|
| **eve** | the agent runtime — durable sessions, tools, hooks, channels |
| **NAMS** | the memory layer — what it knows about *this analyst*, across sessions |
| **Neo4j** | the substrate — memory and world data as one queryable graph |

The single idea the audience should leave with: **the agent is stateless, the
sessions are durable, and the user is remembered somewhere neither of those
owns.** Everything below is evidence for that sentence.

---

## 2. What you need before you start

| Thing | Where | Time | Needed for |
|---|---|---|---|
| Node.js 24+ | `node -v` | — | everything |
| NAMS API key | [memory.neo4jlabs.com](https://memory.neo4jlabs.com) — free | 2 min | everything |
| A model credential | Vercel AI Gateway key, **or** `OPENAI_API_KEY` | 3 min | everything |
| Neo4j Browser tab | [demo.neo4jlabs.com:7473](https://demo.neo4jlabs.com:7473) or your Aura console | 2 min | Act 3 |

**Use a fresh NAMS workspace.** This is the single most likely way the demo
embarrasses you: long-term entities are workspace-scoped, so leftover facts from
earlier testing surface mid-demo and make recall look wrong — the agent
confidently tells your audience that they follow undersea cables.

---

## 3. Setup from zero (~10 minutes)

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations
cd neo4j-agent-integrations/vercel-eve/industry-research-agent
npm install
cp .env.example .env.local
```

Edit `.env.local`. The minimum for the terminal demo is four lines:

```env
NAMS_API_KEY=nams_...              # your fresh workspace's key
AGENT_MODEL=openai/gpt-5.4
OPENAI_API_KEY=sk-...              # or AI_GATEWAY_API_KEY, or run `eve link`
DEMO_USER_ID=alex-analyst         # ← the "who am I" for the whole demo
```

`DEMO_USER_ID` is what makes cross-session recall work without route auth. Set
it to something you will recognise on stage — `alex-analyst`, not
`local-analyst` — because you will read it out of Neo4j Browser in Act 3.

Leave `NEO4J_*` alone: the defaults point at the public demo graph, which is
where every verified answer below comes from.

Confirm the project compiles and eve found everything:

```bash
npx eve info
```

```text
Compile       ready
Diagnostics   0 errors, 0 warnings
Tools         1 tool
```

One tool is correct: `search_news` is the only `defineTool` in the project. The
five `memory-graph__*` tools come from the MCP connection, which is registered
per session and never appears in this count.

---

## 4. Dry run — do this before the room (~10 minutes)

Not optional. Run the whole thing once, end to end, the day before.

```bash
npx eve invoke "My name is Alex and I cover the graph database sector."
npx eve invoke "What sector do I cover, and what is my name?"
```

Each `eve invoke` starts a fresh session, so the second command shares no
transcript with the first. If it answers "Alex, graph databases," memory works
and your demo has a spine. **If it does not, stop and fix it now** — check
`NAMS_API_KEY` is set, then re-run; NAMS entity extraction is asynchronous, so
wait ~15 seconds between the two calls the first time.

Then the same assertion as a test:

```bash
npx eve eval
```

```text
✓  graph/news-search  gates 2/2
✓  memory/cross-session-recall  gates 3/3
```

Finally, warm the graph — the first bolt connection to the shared demo instance
can take a few seconds, and you do not want that pause in Act 1:

```bash
npx eve invoke "What's been written about graph databases?"
```

---

## 5. The demo (~6 minutes)

Clear scrollback. Large font. `npm run dev` for the TUI, or drive it with
`eve invoke` if you prefer visible commands.

### Act 0 — the gap, told by their own CLI *(~40s)*

```bash
npx eve registry search memory
```

> "Three memory integrations. A vector service, Redis, and a note store. I want
> to talk about the one that isn't there."

Opening with *their* tool makes the gap a fact rather than a claim.

### Act 1 — it answers from a graph *(~90s)*

> ⚠️ **Current build:** the only domain tool registered is `search_news`.
> `company_profile` and `company_network` were removed, so the first two
> questions below no longer reach the graph — the model will answer them from
> recall or from a news search. Either re-add those two tools before the demo
> (they are in git history, `agent/tools/`), or run this act with the news
> question alone plus the memory-graph traversal in Act 3.

```
> Who is the CEO of Neo4j, and what industries is it in?
```
✅ *Emil Eifrem. Enterprise Software, Data Analytics, Database Companies…*
— **needs `company_profile`**

```
> Who are Neo4j's competitors?
```
✅ *TigerGraph, OrientDB, Titan, Dato, VESoft…* — **needs `company_network`**

> "That's a traversal, not a column. Nobody stored a 'competitors' field —
> it's `HAS_COMPETITOR` edges, and the model chose the edge to walk."

```
> What's been written about graph database funding?
```
✅ *ArangoDB's $27.8M Series B, Oct 2021, plus related coverage.*

**Two things to have ready.** The dataset ends **mid-2023**, so say "this is a
2023 snapshot of 250k companies" before anyone notices. And the competitor list
has junk in it — one row is an Indonesian car dealer. If it appears, use it:
*"that's a real data-quality artifact in the Diffbot set, and it's exactly the
kind of thing you can see and fix when your knowledge is a graph you can query,
rather than embeddings you can't."*

### Act 2 — it remembers you *(~90s)* ★ the one that sells

```
> My name is Alex and I cover the graph database sector. Keep that in mind.
```

Then, in the TUI:

```
> /new
```

> "`/new` retires the session. The transcript is gone — different session id,
> nothing carried over."

```
> What sector do I cover, and what is my name?
```

*Expected: Alex, graph databases.*

> "There is no memory tool call in that trace. Nothing about remembering was the
> model's decision — a hook on `message.received`, `message.completed`, and
> `turn.completed` stored it because the turn happened. The only path between
> those two sessions is Neo4j."

If you would rather show it as two processes than a TUI command, use the
`eve invoke` pair from step 4 — same proof, more obviously separate.

### Act 3 — it's a graph, not a blob *(~60s)*

Switch to the Neo4j Browser tab already open on your NAMS workspace. Have this
typed and unrun:

```cypher
MATCH (u:User {userId: "alex-analyst"})-[r]-(x)
RETURN u, r, x LIMIT 50;
```

> "Every other memory option returns the fact it matched. This returns the fact,
> what it's connected to, and the path that got there — in the same query
> language as the domain data, because it's the same database."

Then the punchline for their catalog:

> "Co-locate memory with your application graph and a recommendation stops being
> a vector lookup plus a post-filter, and becomes one traversal that carries its
> own explanation."

### Act 4 — it can show its work *(~45s)*

Open [`agent/hooks/persist-reasoning.ts`](industry-research-agent/agent/hooks/persist-reasoning.ts).

> "NAMS has a third memory type: reasoning. We record what the agent was
> thinking, which tools it called, and what came back — from `actions.requested`,
> `action.result`, and `reasoning.completed`. When someone asks 'why did you
> recommend that?', the answer is read back from what was recorded, not
> reconstructed afterwards by the model that is being asked to justify itself."

This is the act that separates the story from "a chatbot with recall."

### Act 5 — how small the ask is *(~45s)*

```bash
npx eve registry view connection/mem0
```

Eight lines of TypeScript in a JSON wrapper. Then show
[`agent/connections/memory-graph.ts`](industry-research-agent/agent/connections/memory-graph.ts).

> "Structurally identical to the mem0 item you already ship. Note the allow-list:
> five read tools out of the forty-eight that server publishes. The writes are
> deliberately excluded — retention is the hook's job — and nine of those tools
> are workspace administration including `workspace_delete`. That's the ask: a
> registry entry, and Neo4j operates the service."

---

## 6. Questions you will get, and the answers

**"Is retrieval semantic?"** Not in the REST path — NAMS search is lexical with
AND semantics and returns no scores, so a paraphrase can miss a fact that is
definitely stored. That is exactly why recall lives in dynamic instructions
resolved on `turn.started`: it searches the user's own words rather than the
model's paraphrase of them. Vector retrieval is the roadmap item we most want to
talk about.

**"What about multi-tenancy?"** Conversations scope per user correctly.
Long-term entities are workspace-scoped and carry no user id, so two users in
one workspace can surface each other's facts — we reproduced it with four test
identities. The answer today is one NAMS workspace per tenant;
`workspaceIdFor(userId)` is the seam, and it works because the gateway keeps one
`MemoryClient` per user. Raise this before they find it.

**"Could this just be a tool the model calls?"** It could, and most memory demos
ship it that way. A tool-driven agent retains only when the model remembers to
call `remember` — reliable for a few turns, then quietly not. Hooks make
retention a property of the turn.

**"Does this lock us into Vercel?"** No. `eve build` writes a Nitro server that
runs on any Node host; only the Workflow world changes.

**"Who operates it, what does it cost?"** Neo4j Labs runs the hosted service;
keys are free. Or point it at your own Aura instance.

**"What happens if NAMS is down?"** The turn still answers. Every memory call is
wrapped — a thrown hook fails the turn in eve, so an outage costs a personalized
answer, never the answer.

**"Can I see what it knows about me / delete it?"** Yes, and that is the
co-location argument: it is rows in Neo4j Browser, and forgetting is deleting an
edge.

---

## 7. When it breaks

| Symptom | Cause | Do this |
|---|---|---|
| "I don't have any stored memory about that" right after storing | entity extraction is asynchronous | wait ~15s, or ask using the user's original nouns — retrieval is lexical |
| Recall returns *someone else's* facts | shared NAMS workspace | you skipped the fresh workspace; switch keys, or own it as the multi-tenancy answer in §6 |
| First graph question hangs | cold bolt connection to the shared demo instance | you skipped the warm-up in step 4; keep talking, it lands |
| Agent says a company doesn't exist | exact-name matching, then a full-text fallback | try the shorter form — "Neo4j" not "Neo4j Inc." |
| A nonsense competitor appears | real Diffbot data-quality artifact | use it (see Act 1) |
| An org question is answered from model recall, not the graph | `company_profile` / `company_network` are not registered in this build | only `search_news` ships today — re-add them from git history if the demo needs them |

**Total network failure.** Acts 3, 4 and 5 need no live model call — the Neo4j
Browser tab, the hook source, and the connection file all still land. Walk the
code and a recorded trace instead. Know this before you need it.

---

## 8. Reset between runs

```bash
# New identity = clean memory, without touching the workspace
sed -i 's/^DEMO_USER_ID=.*/DEMO_USER_ID=alex-demo-2/' .env.local
```

Changing `DEMO_USER_ID` is the fastest reset: it is the memory key, so a new
value is a new person with no history. Update the Act 3 Cypher to match.

To wipe properly, delete and re-provision the NAMS workspace from
[memory.neo4jlabs.com](https://memory.neo4jlabs.com) — but re-run the step 4 dry
run afterwards, because you now have an empty graph and no rehearsed state.

---

## Reference

- [`TUTORIAL.md`](TUTORIAL.md) — build this agent from an empty directory
- [`PITCH_AND_DEMO.md`](PITCH_AND_DEMO.md) — the argument, the objection handling, the ask
- [`README.md`](README.md) — integration reference and known limitations
- [`industry-research-agent/`](industry-research-agent/) — the project you are demoing
