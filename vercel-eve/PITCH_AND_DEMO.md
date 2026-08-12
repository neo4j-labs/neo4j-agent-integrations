# Pitching Vercel: graph-native memory for eve

How to demo `vercel-eve/` and make the case for a Neo4j entry in eve's
integration catalog.

**Audience:** the eve team, DevRel, or partnerships at Vercel.
**Duration:** ~20 min (6 min demo, rest is framing and Q&A).
**Deliverable we want out of the meeting:** agreement on which registry item
shape to submit, and the contact who reviews it.

---

## 1. The ask, up front

Say this in the first ninety seconds. Do not save it for the end.

> eve tells developers that durable session state is not memory, and points
> them at the integration catalog for a real store. The catalog has three
> memory options today and none of them is a graph. We've built the graph one,
> it's running, and it's about eight lines of code to install. We'd like it in
> the catalog — and we want to know which shape you'd rather review: a
> connection item or an extension.

Three things we want:

1. **A registry listing** — `connection/nams`, `extension/nams`, or both.
2. **The review path** — issue first, or PR straight to the registry?
3. **Design feedback** on the extension mount, while it's still cheap to change.

What we are *not* asking for: engineering time, roadmap commitments, or
co-marketing as a precondition.

---

## 2. The story in one paragraph

An agent that cannot remember its user is a demo, not a product. eve solved
durability — sessions survive crashes, redeploys, and days-long gaps — and was
explicit that this is *not* memory: anything that outlives the session belongs
in an external store. The stores on offer are key/value and vector. But what an
agent needs to recall is mostly relational: this analyst follows these sectors,
which contain these companies, which compete with those, which appeared in
these articles. A flat store returns the fact it matched. A graph returns what
that fact is connected to, and can name the path that produced it. NAMS keeps
memory as nodes and edges in Neo4j, so memory and domain knowledge are
queryable together.

---

## 3. Why Vercel should care

Verified on the live catalog the day this was written:

```
$ eve registry search memory
eve (4 results)
  mem0               connection/mem0            Persistent memory for AI agents and assistants.
  upstash-agentkit   extension/upstash-agentkit Add long-term memory, Redis Search, and durable chat history…
  arcana             extension/arcana           Give an eve agent a workspace-scoped long-term memory…
  chat-sdk-kapso     channel/chat-sdk-kapso     (not memory)
```

Three memory integrations. A hosted vector service, Redis, and a workspace
note store. **No graph.** Meanwhile eve's own extensions documentation uses
memory as the archetypal extension example: *"A memory extension could use
hooks to capture context and tools to recall it."*

The argument for Vercel, in their terms:

- **A gap in the catalog they already named.** They wrote the memory-extension
  example; nobody shipped the graph version.
- **It exercises four eve primitives at once** — dynamic model resolution,
  dynamic instructions, hooks, and dynamic tools. Good pressure on the API
  surface, and a reference implementation for anyone else building memory.
- **Zero platform work.** It's a package plus a registry JSON. Neo4j operates
  the service.
- **A developer audience that isn't already theirs.** Neo4j's community skews
  Java/Python/data-engineering — people who don't reach for Vercel first.

---

## 4. Pre-flight

Do this **before** the meeting, on the machine you'll present from. The demo
calls a model provider, NAMS, and a Neo4j instance over the network; all three
need to work from your seat.

```bash
cd vercel-eve/industry-research-agent
npm install
cp .env.example .env.local      # add NAMS_API_KEY (free: memory.neo4jlabs.com)
                                # add AI_GATEWAY_API_KEY or OPENAI_API_KEY

npx eve info                    # expect: Compile ready, 0 errors, 3 tools
npx eve eval                    # expect: 2 passed
```

Checklist:

- [ ] `eve eval` passes both evals — especially `memory/cross-session-recall`.
- [ ] `DEMO_USER_ID` is set to something recognisable, not `local-analyst`.
- [ ] **Use a fresh NAMS workspace.** Long-term entities are workspace-scoped,
      so leftover test facts from other users will surface mid-demo and make
      recall look wrong. This is the single most likely way the demo embarrasses
      you.
- [ ] Neo4j Browser open on the NAMS workspace in a second tab, already
      authenticated, with the memory query typed but not run.
- [ ] A terminal with a large font and scrollback cleared.
- [ ] Know your fallback: if the network dies, walk the code and the recorded
      trace instead. Beats 2, 5, and 6 need no live model call.

---

## 5. The demo (~6 minutes)

Six beats. Each has a point to land — say it out loud; don't assume the
terminal makes it for you.

### Beat 1 — the gap, told by their own CLI *(~40s)*

```bash
npx eve registry search memory
```

> "Three memory integrations. A vector store, Redis, and a note store. I want
> to talk about the one that isn't there."

Opening with *their* tool rather than our slide makes the gap a fact rather
than a claim.

### Beat 2 — memory in one line *(~60s)*

Open [`agent/agent.ts`](industry-research-agent/agent/agent.ts).

```ts
model: defineDynamic({
  fallback: MODEL_ID,
  events: {
    "step.started": (_event, ctx) => {
      const model = baseModel();
      return MEMORY_MODE === "wrap" ? nams().wrap(model, memoryScope(ctx)) : model;
    },
  },
}),
```

> "That's the whole integration in `wrap` mode. Memory is a property of the
> model, so the harness, the tools, and the channels never learn it exists.
> Nothing else in the project changes."

Worth naming: `step.started` is the only scope allowed to return a live model
object — session- and turn-scoped selections get serialized, so they must be id
strings. Mentioning this signals we read the framework properly, and it's a
constraint their docs could state more loudly.

### Beat 3 — the money shot *(~90s)*

Two separate processes. No shared transcript.

```bash
npx eve invoke "Remember this about me: my research beat is undersea cable operators."
npx eve invoke "What is my research beat?"
```

> "Every `eve invoke` is a new session. The second command shares no
> conversation history with the first — the only path between them is the
> graph."

Then lock it down as a regression test:

```bash
npx eve eval
```

> "`memory/cross-session-recall` stores a fact, calls `t.newSession()` to throw
> the transcript away, and asserts the agent still knows it. That assertion is
> the line between memory and a long context window — and it runs against the
> real HTTP surface, on your eval harness."

**This is the beat that sells.** If you have time for one thing, this is it.

### Beat 4 — it's a graph, not a blob *(~60s)*

Switch to Neo4j Browser on the NAMS workspace and run the pre-typed query.

> "Every other memory option returns the fact it matched. This returns the
> fact, what it's connected to, and the path that got there. Same query
> language as the domain data, because it's the same database technology."

Then the punchline for their catalog:

> "Co-locate memory with your application graph and a recommendation stops
> being a vector lookup plus a post-filter and becomes one traversal that
> carries its own explanation."

### Beat 5 — the agent can show its work *(~45s)*

Show a recorded reasoning trace: one step per reasoning block, with the tool
calls hanging off it, arguments intact.

> "NAMS has a third memory type: reasoning. We record what the agent was
> thinking, which tools it called, and what came back — from
> `actions.requested`, `action.result`, and `reasoning.completed`, so it never
> depends on the model choosing to log anything. When a user asks 'why did you
> recommend that?', the answer is read from what was recorded, not
> reconstructed by the model afterwards."

Point at [`agent/hooks/persist-reasoning.ts`](industry-research-agent/agent/hooks/persist-reasoning.ts).
This is the beat that separates us from "a chatbot with recall."

### Beat 6 — how small the ask is *(~60s)*

```bash
npx eve registry view connection/mem0
```

Eight lines of TypeScript inside a JSON wrapper. Then show the NAMS
equivalent — verified live against `https://memory.neo4jlabs.com/mcp`
(Streamable HTTP, `initialize` → 200, `tools/list` → 35 tools):

```ts title="agent/connections/nams.ts"
import { defineMcpClientConnection } from "eve/connections";

export default defineMcpClientConnection({
  url: "https://memory.neo4jlabs.com/mcp",
  description: "Neo4j Agent Memory: store and recall persistent memory as a graph.",
  auth: { getToken: async () => ({ token: process.env.NAMS_API_KEY! }) },
  tools: { allow: ["memory_get_context", "memory_add_messages", "memory_add_entity"] },
});
```

> "Structurally identical to the mem0 item you already ship. That's the ask."

---

## 6. The two paths in — bring both, recommend one

Put this on one slide and let them choose. Having a preference *and* a second
option reads as prepared rather than pushy.

| | `connection/nams` | `extension/nams` |
|---|---|---|
| Shape | MCP connection, like `connection/mem0` | Packaged tools + hooks + instructions |
| Consumer install | `eve add connection/nams` | `eve add extension/nams` |
| Memory is | tools the model must choose to call | transparent; hooks retain deterministically |
| Registry JSON | ~20 lines | small item + a published npm package |
| Ships | immediately | after we publish `@neo4j-labs/nams-eve` |
| Precedent in catalog | `connection/mem0` | `extension/arcana`, `extension/upstash-agentkit` |

**Recommend the connection first, the extension second.** The connection is
reviewable in one sitting and has an exact precedent. The extension is the
better product — deterministic retention beats hoping the model calls a tool —
but it needs the package published first.

Two caveats to raise *before* they find them, because both are real:

- The NAMS MCP surface includes destructive `workspace_delete` and
  `workspace_reprovision`. `tools.allow` is not optional in that item; we'd
  ship it allow-listed.
- No header binds a workspace, so the item needs a workspace-bound key or
  `workspace_id` passed per call.

**We don't need permission to start.** `eve registry add` takes any
`{name}`-templated URL, so Neo4j can publish `@neo4j` as a third-party source
today and developers can install from it:

```bash
eve registry add @neo4j=https://registry.neo4j.com/eve/{name}.json
eve add @neo4j/nams
```

Use this to reframe the ask: it isn't "please unblock us," it's "we're
shipping either way — the catalog is how your users find it."

---

## 7. Q&A prep — the hard ones

Lead with the limitation before they find it. This audience will read the code.

**"How does this isolate tenants?"** *(the one that can sink the pitch)*
Conversations scope by user correctly, derived from `ctx.session.auth` — no
tool accepts a `userId`, so a prompt-injected document can't address another
user's memory. But **facts written to the long-term graph carry no user id**,
so users sharing a workspace can read each other's stored facts. We reproduced
it: four test identities each stored one preference, and the fourth was told it
focused on all four. The answer today is one NAMS workspace per tenant, passed
as `NAMS_WORKSPACE_ID`. Fix is tracked upstream at
[neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory). Say this
plainly; it's in our README already, and being first to raise it is worth more
than hoping it doesn't come up.

**"Is retrieval semantic?"** Not yet — NAMS search is lexical with AND
semantics and returns no scores, so a paraphrase can miss a fact that is
definitely stored. This is exactly why `wrap` and `hooks` beat `tools`: they
retrieve against the user's own words, while `tools` lets the model paraphrase,
and models paraphrase constantly. Vector retrieval is the roadmap item we'd
most like to talk about.

**"Who operates it, and what does it cost?"** Neo4j Labs runs the hosted
service at memory.neo4jlabs.com; keys are free. Or point it at your own Aura
instance and Neo4j operates nothing. No Vercel infrastructure either way.

**"What happens when NAMS is down?"** The agent degrades, it doesn't fail.
Recall is wrapped in try/catch and returns nothing; retention warns and drops
the write. A thrown hook fails the eve turn, so every store call is guarded —
worth saying out loud, because it's a real eve footgun.

**"Duplicate writes?"** Hooks are at-least-once: an interrupted turn re-runs
its step and re-emits events. eve's guidance is to key on `event.meta.id`;
NAMS has no dedupe key, so we budget for occasional duplicates. Honest gap.

**"Why three modes? Pick one."** Fair. `wrap` is the default and the one to
ship. The other two exist because this repo's job is to map every attachment
point a platform offers — and because `hooks` is what a packaged extension
would actually use. Exactly one is ever active, so no turn is stored twice.

**"Does this work outside Vercel?"** Yes, any Node host — which is worth
saying, because it means we're not asking them to carry a lock-in story.

**"Is eve's API stable enough for you?"** It's beta and we expect churn. Three
constraints bit us silently and are worth reporting as docs feedback: only
`step.started` may return a live model object; dynamic-tool `execute` must be
an inline function expression or it breaks after a resume; a thrown hook fails
the turn.

---

## 8. Close

> "The catalog has a vector store, a Redis store, and a note store. The graph
> one is built, it passes a cross-session recall eval against the real HTTP
> surface, and it installs in eight lines. Which shape do you want to review?"

Then stop talking.

**Leave-behind:** [`README.md`](README.md) (integration reference, including the
limitations above), [`TUTORIAL.md`](TUTORIAL.md) (build it yourself in eight
steps), and this repo path.

**Follow up within 48h** with the registry JSON attached, whichever shape they
picked.

---

## 9. Links

- Working project: [`industry-research-agent/`](industry-research-agent/)
- Integration reference: [`README.md`](README.md) · Tutorial: [`TUTORIAL.md`](TUTORIAL.md)
- [Give Your Vercel Eve Agent a Memory](https://lyonwj.com/blog/agent-memory-with-eve-and-nams) — the narrative version, built around [TrailGraph](https://github.com/johnymontana/trailgraph)
- [NAMS](https://memory.neo4jlabs.com) · [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider)
- [eve docs](https://vercel.com/docs/eve) · [Install integrations](https://vercel.com/docs/eve/install-integrations) · [vercel/eve](https://github.com/vercel/eve)
- Same memory package on the AI SDK directly: [`../vercel-agent/`](../vercel-agent/)
- Demo database: `neo4j+s://demo.neo4jlabs.com:7687` (companies/companies)
