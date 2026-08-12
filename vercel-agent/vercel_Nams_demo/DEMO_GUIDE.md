# NODES Session Guide — Graph-Native Memory for the Vercel AI SDK

**Format:** 30 minutes, ~11 min live demo, 3 min Q&A
**Demo app:** `vercel_Nams_demo` (Next.js 14 + Vercel AI SDK v7 + NAMS)
**Package:** `@neo4j-labs/nams-ai-provider@0.2.0`

> Everything in the demo script below was executed against the live app and the
> hosted NAMS service on the staged workspace. Verified outputs and real timings
> are quoted throughout. **There are no known-failing paths in this script** —
> the three failure modes we found are fixed **in the package itself**
> (`nams-provider-fixes.patch`, 42 tests green) and re-verified end to end (§9).

---

## 1. The story in one paragraph

Every production chat agent has the same flaw: a user spends twenty minutes explaining their stack and preferences, the session ends, and tomorrow the agent greets them as a stranger. Context windows keep growing, but a context window is a *working set*, not a memory. `@neo4j-labs/nams-ai-provider` closes that gap for the Vercel AI SDK — a graph-native memory layer backed by the hosted Neo4j Agent Memory Service, added with a one-line model swap. This app is the reference client: the same agent wired three different ways, with the memory rendered on screen so you can watch it work.

---

## 2. What the application does

A Next.js chat app where **memory is a visible UI component**, not an invisible backend detail.

| Element | What it shows |
|---|---|
| **Memory Panel** | Chips above each answer — `3 recent · 2 observations · 1 reasoning`. Expands into three tabs, one per NAMS tier |
| **Reasoning Trace** | Per-step record: what the agent thought, which tool it called, what came back |
| **Chat** | Neo4j Design Language components, streaming tokens, tool calls rendering as they resolve |
| **Session identity** | A UUID in `localStorage` → sent as `userId`. Refresh ≠ reset; it's session two |

The panels are the point. Any chat demo can claim the agent remembers your name. This one lets the audience *count* the memories, read them, and see which tier each came from.

It also connects to a **live Neo4j database over MCP**, so the same agent answers both "what do you know about me?" (memory) and "how many Organization nodes are in my database?" (Cypher).

---

## 3. What the NAMS package does

`@neo4j-labs/nams-ai-provider` sits between the AI SDK and the NAMS REST client and ships **three integration modes over one client**:

| Mode | Call | Memory handling | Visible in UI? |
|---|---|---|---|
| **provider** | `createNamsProvider({ baseProvider, scope }).languageModel(id)` | Middleware injected by the provider | No |
| **middleware** | `createNams().wrap(model, scope)` | Same middleware, on a resolved model | No |
| **tools** | `createNams().toolsWithMcp(scope, mcpConfig?)` | `query_memory` + `store_memory` the model drives | **Yes** |

The trade in one line: **middleware guarantees memory, tools mode makes it visible.**

**Three memory tiers**, and the split shapes everything:
- **Short-term** — the conversation, searchable within *and across* sessions for a user
- **Long-term** — the graph: entities, facts, preferences as typed nodes
- **Reasoning** — the decision trail, which makes the agent auditable after the fact

Plus `enforceQueryMemory()`, a `prepareStep` guard that holds the loop at `toolChoice:'required'` until `query_memory` has run, then forces it after `graceSteps`. Because tool descriptions are advisory — models skip bookkeeping calls.

---

## 4. How this contributes to the Vercel ecosystem

This is the framing that lands with an AI-SDK-literate audience:

**The AI SDK offers library authors three extension points, and NAMS implements all three:**

| AI SDK extension point | What NAMS does with it |
|---|---|
| `ProviderV4` | Registrable, swappable, composes with `createProviderRegistry` |
| `LanguageModelV4Middleware` | `transformParams` / `wrapGenerate` / `wrapStream` — read before, write after |
| `tool()` | Zod-validated memory tools, visible in the UI stream |

Most memory providers pick one shape. Mem0 wraps the model — invisible, but the model can't reach for memory deliberately. Supermemory and Hindsight expose tools — visible and model-driven, but never guaranteed. Letta hosts the agent. **NAMS gives you the wrapper *and* the tools over one client and one API key**, so "guaranteed vs. visible" becomes a code-level decision you can change in an afternoon — or refuse to make, via hybrid.

**And the store is a graph, not a document collection.** Every provider on that list answers "what did the user tell me about X?" — that's vector search over text, table stakes. A graph answers what the text never stated in one place: which of this user's colleagues use the tool they just complained about; what connects March's decision to today's bug. Those are traversals, not lookups.

> **The concrete ask:** the AI SDK's Memory Providers docs page lists Letta, Mem0, Supermemory, Hindsight, and MongoDB — **none graph-backed**. We want NAMS to be the graph option on that page. Mentioning this on stage is a legitimate call to action.

---

## 5. Why we built it, and why it's useful

**Why:** Memory is the difference between an agent that answers questions and an agent that knows who's asking. The AI SDK gives you a durable *loop*; it doesn't give you a durable *mind*. And the usual fix — stuff more into the context window, summarise the rest — fails in the least useful direction: the thing you needed is what got summarised away.

**Why a graph specifically:** Similarity search answers exactly one question — *what have I seen that reads like this?* It doesn't know Priya is a person, Acme is an organization, that she works *at* Acme, or that "concise, technical answers" is a standing instruction rather than a passing remark. Every one of those is a relationship, and a flat pile of snippets has nowhere to put relationships. **Vector stores give recall; the graph gives understanding.**

**Where it pays off:**
- **Support that never asks twice** — plan, environment, prior tickets surface automatically
- **Assistants with continuity** — typed `user_preference` memories with confidence scores, across devices
- **Agent fleets sharing one brain** — research, coding, and scheduling agents reading the same user graph
- **Auditable reasoning** — reasoning traces are a first-class retrieval source, and it's all Cypher-queryable when the agent can't answer for itself

---

## 6. Code walkthrough for the live demo

Four files. Keep each on screen ~45 seconds.

### 6.1 The mode switch — [`app/api/chat/route.ts`](app/api/chat/route.ts)

```typescript
const resolvedModel = mode === 'provider'
  ? createNamsProvider({ ...memoryConfig, baseProvider: openai, scope }).languageModel(MODEL_ID)
  : mode === 'middleware'
    ? createNams(memoryConfig).wrap(openai(MODEL_ID), scope)
    : openai(MODEL_ID);
```

**Say:** "One env var picks the seam. Note the third branch — in tools mode the model is deliberately *unwrapped*. Memory doesn't happen to it; it happens because the model asks."

### 6.2 Memory + database in one tool set

```typescript
const namsResult = await createNams(memoryConfig)
  .toolsWithMcp(scope, getNamsMcpConfig());
```

**Say:** "`query_memory` and `store_memory` merged with every Neo4j MCP tool, behind a single `close()`. Two tool sources, one teardown."

### 6.3 The guard that makes memory non-optional

```typescript
prepareStep: enforceQueryMemory({ graceSteps: 2 })
```

**Say:** "Models skip bookkeeping tools. This holds the loop until `query_memory` has run. Two steps of grace, not zero — an agent with database tools legitimately wants a schema lookup first."

### 6.4 Memory as a UI component — [`utils/message.ts`](utils/message.ts)

```typescript
const mems = out?.memories ?? [];
const recent       = mems.filter(m => m.source === 'conversation');
const observations = mems.filter(m => m.source === 'long-term');
const reasoning    = mems.filter(m => m.source === 'reasoning');
```

**Say:** "No special endpoint. `query_memory` is an ordinary tool call, so its output is already in the stream. Three sources, three tabs. This is *why* tools mode exists."

### 6.5 Prompts built from observed capability — [`lib/constants.ts`](lib/constants.ts)

```typescript
const dbToolNames = Object.keys(tools ?? {}).filter(
  name => name !== 'query_memory' && name !== 'store_memory',
);
```

**Say (great throwaway line):** "`MCP_URL` being set tells you someone *intended* a connection. It tells you nothing about whether one exists. We generate the prompt from the tools that actually came back."

---

## 7. Pre-flight — do this before you present

> **Non-negotiable. The demo silently degrades without these.**

**A. Use a MANAGED workspace.** Semantic retrieval only works on `db_mode=managed`. On an `external` workspace, NAMS falls back to case-sensitive substring matching on entity *names*, and natural-language questions return nothing. This is invisible from the API surface — same code, different recall.

```bash
# already provisioned and seeded for you:
MEMORY_WORKSPACE_ID='fdccbafa-9292-4aab-b041-5f70a4e3265f'   # "nodes-demo" — provisioned, seeded, verified
```

**B. Use a CLEAN workspace.** Long-term entities are workspace-global with no per-user filter. Leftover entities from other tests bleed into recall — in testing the agent said *"I also have memories about other people, like Alex"*. One workspace per demo.

**C. Seed 90 seconds early.** Embedding indexing is asynchronous. The identical question failed and then succeeded ~60s later. Run turns 1–2 before you go on stage, or during the slides.

**D. Config:**
```env
NAMS_MODE=tools                      # panels only render in tools mode
OPENAI_MODEL=gpt-5.4-mini
NAMS_EXTRACTION_MODEL=gpt-5.4-mini   # builds the entity graph
MCP_URL=...  MCP_BEARER_TOKEN=...    # live database tools
```

**E. Have a browser tab open on the NAMS console** showing the entity graph — that's the payoff shot.

---

## 8. The demo script (~11 minutes)

### Turn 1 — Introduce yourself *(~25s)*

> **Hi! I'm Priya, a graph data engineer at Acme Analytics in Bangalore. I work mostly in Python and I prefer concise, technical answers.**

**Verified reply:** *"Hi Priya — nice to meet you. Got it: you're a graph data engineer at Acme Analytics in Bangalore, you work mostly in Python, and you prefer concise, technical answers."*

**Point at:** the Memory Panel appearing, and the Reasoning Trace showing `query_memory → answer`.

The model may or may not call `store_memory` on this turn — either is fine now. When it skips, `ensureStored()` persists the turn in `onFinish`, and the log says so: `store_memory skipped by model — persisted turn in onFinish`. **Nothing is lost either way.**

### Turn 2 — Make it save *(~29s)*

> **Please save all of that to long-term memory: my name, role, employer, city, language, and answer-style preference.**

**Verified reply:** *"Saved to long-term memory. I've stored: name: Priya, role: graph data engineer, employer: Acme Analytics, city: Bangalore, preferred language: Python, answer style: concise, technical."*

**Point at:** `store_memory` in the Reasoning Trace. Server log shows `stores=1`.

### Turn 3 — THE MONEY SHOT: refresh, then recall *(~20s)*

**Hard-refresh the browser first.** Say: *"New page, new React tree, everything in component state is gone. The session id came back from localStorage — so as far as the agent is concerned, this is session two."*

> **What do you remember about me?**

**Verified reply:**
> I remember a few things about you from prior context:
> - Your name is **Priya**
> - You're a **graph data engineer**
> - You work at **Acme Analytics**
> - You're in **Bangalore**
> - You prefer **Python**
> - You prefer **concise, technical answers**

**Point at:** the *observations* tab — these came from the long-term graph, not the chat history.

### Turn 4 — Memory is not the database *(~6s, fastest turn)*

> **How many Organization nodes are in my Neo4j database?**

**Verified reply:** *"There are **46,088 Organization nodes** in your Neo4j database."* — 5.7s, `db=[get-schema, list-gds-procedures, read-cypher]`

**Say:** "Same agent, same loop, completely different source. Memory holds what was *said*. The database holds what is *true about the world*. If you don't draw that line in the prompt, the model draws it badly — ours would call `query_memory`, get `found:false`, and apologise while sitting on a live Cypher connection."

### Turn 5 — Show the graph *(~45s, no typing)*

Switch to the NAMS console / entity search. **Verified contents of the demo workspace:**

```
Priya                          [Person]
Acme Analytics                 [Organization]
Bangalore                      [Location]
Python                         [ProgrammingLanguage]
graph data engineer            [Concept]
concise, technical responses   [preference]
```

**Say:** "This is the difference. Not six sentences in a vector index — six typed nodes. `Python` was classified `ProgrammingLanguage` by the extraction model. That's a graph you can run Cypher against, join to your domain data, and audit."

---

## 9. Questions to invite from the audience (safe) — and what to avoid

**All verified passing** on the staged workspace, with the reliability layer in
[`lib/nams-enrich.ts`](lib/nams-enrich.ts) active. Take these from the audience with confidence:

| Question | Verified answer |
|---|---|
| "What do you remember about me?" ⭐ | Full profile — name, role, employer, city, language, preference. Stable across 3 consecutive runs |
| "What's my name?" | *"Your name is Priya."* |
| "Which programming language do I prefer?" | *"You prefer **Python**."* |
| "Where am I based?" | *"You're based in **Bangalore**."* |
| "Who do I work for and what is my role?" | *"**Acme Analytics**, and your role is **graph data engineer**."* |
| "How many Organization nodes are in my Neo4j database?" | *"**46,088**"* — with a live Cypher count |

**Why these work now.** Three defects blocked them. **All three are fixed in the
package itself** (`nams-provider-fixes.patch`), not worked around in the demo —
so an audience member who runs `npm install` gets the same behaviour you demo:

1. **`query_memory` dropped entity names.** `retrieveMemories` built each hit as
   `content: e.description ?? e.name`, so an entity named `Python` described as
   "Preferred language" reached the model as just "Preferred language". The agent
   answered *"the memory doesn't specify which one"* — and would half-reconstruct
   names it never saw: **"You're based in *Ban*."** Hits now carry
   `name — description`, and dedupe still keys on the description so a fact stored
   as both message and entity collapses to one.
2. **Graph extraction never ran on OpenAI.** `description: z.string().optional()`
   in the extraction schema is rejected by OpenAI's strict structured-output mode,
   so every call failed and silently fell back to a flat entity. The field is now
   required with an empty-string convention.
3. **Memory could extract its own output.** When the agent answers "here's what I
   remember" and that gets stored as a fact, extraction minted entities like
   `long-term memories [Concept]`, which then outranked real facts on the next
   recall — compounding every time the question was asked. `isSelfReferential()`
   drops them at write time.

The one thing still handled demo-side is [`ensureStored()`](lib/nams-enrich.ts):
the tool loop ends when the model emits text, so there is no later step in which
`store_memory` could be forced the way `enforceQueryMemory` forces a query. That
is documented package behaviour, and inspecting the turn in `onFinish` is the
remedy the package recommends.

## 10. Architecture Q&A prep

**Q: Why a graph instead of a vector database?**
Similarity search answers "what reads like this?" A graph answers "what is connected to what." Retrieval that can't traverse can't answer "which of my colleagues use the tool I complained about." Vector stores give recall, the graph gives understanding. Also: it's Neo4j underneath, so memory is Cypher-queryable outside the agent — audit what it learned, debug an odd recall, run analytics across your user base.

**Q: How do you scope memory to a user? Is it multi-tenant?**
Conversation memory is scoped by `userId` and resolved by precedence: explicit `conversationId` → per-instance cache → the user's most recent conversation → create new. **Be honest:** long-term *entities* are workspace-global today, with no server-side per-user filter — which is why we use one workspace per demo. For real multi-tenancy today you'd provision a workspace per tenant.

**Q: What happens if NAMS is down?**
The package's core invariant: if memory breaks, the model call still succeeds. Every retrieval and persistence failure degrades to a logged warning, never a thrown error in the request path. We saw this live — a transient `add_entity` backend error cost personalisation for one turn, not the turn.

**Q: Latency cost?**
Retrieval fans out across four sources **in parallel**, deduped, ranked, capped at `maxMemories` (default 6, hard ceiling 12). Measured turns: 5.7s for a database question, ~20–30s for turns doing query + store + extraction. `extractionModel` adds one model call *per stored memory* — that's the dominant cost, and it's off by default.

**Q: Why three modes? Isn't that indecision?**
It maps to where memory sits in *your* control flow. Provider mode if you construct models from a provider — one-string change. `wrap()` if models are already resolved from a registry or per-tenant config. Tools mode when the memory cycle must be inspectable by users. They compose too: wrap for a guaranteed baseline, add tools for model-driven top-ups.

**Q: Isn't the reasoning trace just the model narrating?**
No, and this is the important part — nothing asks the model to explain itself. The trace is assembled from the step objects the SDK already produced: `reasoning`, `actionTaken`, `result`. It can be wrong about *why*. It cannot be wrong about *what*.

**Q: How does this compare to Mem0 / Supermemory / Letta?**
Mem0 wraps the model (invisible, not deliberate). Supermemory/Hindsight expose tools (visible, not guaranteed). Letta hosts the agent. NAMS ships both shapes over one client — and backs them with a graph rather than a document collection. Where it's a *worse* fit: if you want memory tiers designed for you, MongoDB's split is well thought through; NAMS gives you a typed graph and expects you to have opinions.

---

## 11. Technical Q&A prep — the hard ones

**Q: What broke while building this?**

Four things worth naming, all real:

1. **The model skipped `query_memory`** because it saw the answer in visible history. Fixed with `enforceQueryMemory({ graceSteps: 2 })` — a `prepareStep` is a mechanism, a system prompt is a suggestion.
2. **`found:false` read as "unknown."** The agent apologised while holding a live Cypher connection. Fixed by separating the two meanings explicitly in the prompt.
3. **Hardcoded MCP tool names.** Worked locally with `mcp-neo4j-cypher`, broke against hosted Aura which exposes different names. Now generated from what the server reported at connect time.
4. **Graph extraction silently never ran.** The package's extraction schema marks `description` optional; OpenAI's strict structured-output mode requires every property in `required`, so every call failed and fell back to a flat entity. We fixed it demo-side by relaxing `strictJsonSchema` via `defaultSettingsMiddleware`; the upstream fix is dropping `.optional()`.

**Q: Are typed relationships written to the graph?**
Not via the hosted REST API today — `add_relationship` raises `NotSupportedError: supported by BridgeTransport only`. The extractor produces `WORKS_AT`-style edges but they don't persist through the hosted path; entities land, edges come from the server's own pipeline as generic `RELATED_TO`. **Don't promise typed relationships on stage.**

**Q: Duplicate entities?**
Yes — we saw `Python` as both `ProgrammingLanguage` and `SoftwareTool`, and `Bangalore` as both `Location` and `place`. Entity resolution is a review queue (`memory_review_queue`, `memory_resolve_entity` for SAME_AS pairs), not automatic. Repeated demo runs multiply entities.

**Q: Extraction noise?**
Extraction runs over stored interaction text, and when that text contains memory-system output you get entities like `query_memory [SoftwareTool]` — the extractor eating its own tail. Storing typed *facts* rather than raw interactions produces clean entities.

**Q: How is the demo tested?**
18 route-level tests against a fully mocked package — mode wiring, MCP fallback, `enforceQueryMemory` applied in tools mode *and not otherwise*, prompt built only from returned tool names. ~1s, no API keys. The honest caveat: because it mocks the package, it stays green through exactly the upgrade that breaks you. A major AI SDK bump sails through all 18 and dies on the first `tsc`. Run both; after a dependency bump trust the typechecker first.

**Q: Why `--legacy-peer-deps`?**
`@neo4j-ndl/react` pins React 18 while some AI SDK packages advertise React 19.

**Q: Can I run memory in my own Aura instead of NAMS-managed?**
Yes — `db_mode=external`. **But** you lose vector similarity, so retrieval degrades to substring matching on entity names, silently. That's the real trade: colocation with your domain data, or working semantic recall. Today you can't have both.

---

## 12. Timing plan

| Min | Section | Slides |
|---|---|---|
| 0–3 | The problem: agents forget | 1–3 |
| 3–7 | Memory isn't embeddings, it's a context graph — three tiers | 4–6 |
| 7–12 | The package: three AI SDK extension points, three modes | 7–10 |
| 12–23 | **LIVE DEMO** (turns 1–5) | — |
| 23–27 | What we learned — the four bugs | 11–13 |
| 27–30 | Ask + Q&A | 14–15 |

**If you lose time,** cut turn 5 (show the graph as a screenshot on a slide instead) — the refresh-and-recall moment in turn 3 is the one that must survive.

---

## 13. Links

- Demo source — `vercel-agent/vercel_Nams_demo`
- [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider)
- [NAMS](https://memory.neo4jlabs.com) — free API key
- [A Tour of NAMS](https://medium.com/neo4j/a-tour-of-the-neo4j-agent-memory-service-nams-0f2d535a4fdb) — William Lyon
- [Give Your Vercel Eve Agent a Memory](https://lyonwj.com/blog/agent-memory-with-eve-and-nams)

---

## 14. Pre-demo smoke test — all three modes

Run this once end-to-end before the talk. ~10 minutes. Every output below was
observed on the staged workspace with the patched package installed.

### Step 0 — Guard the patched package (do this first)

The three package fixes are installed as a **local build** in `node_modules`, not
from npm. **`npm install` / `npm ci` will silently overwrite them** and the "Ban"
bug comes back. Verify before every demo:

```bash
node -p "require('fs').readFileSync('./node_modules/@neo4j-labs/nams-ai-provider/dist/index.js','utf8').includes('isSelfReferential')"
# must print: true
```

If it prints `false`, rebuild and reinstall:

```bash
cd <agent-memory>/typescript/packages/vercel-ai-provider && npm run build
cp dist/* <demo>/node_modules/@neo4j-labs/nams-ai-provider/dist/
```

Once 0.2.1 is published, this whole step goes away — bump the dependency instead.

### Step 1 — Confirm config

```bash
grep -E "NAMS_MODE|MEMORY_WORKSPACE_ID|OPENAI_MODEL|NAMS_EXTRACTION_MODEL" .env
```

Expected: `NAMS_MODE=tools`, the `nodes-demo` workspace id, `gpt-5.4-mini` for both models.

### Step 2 — Static checks

```bash
npx tsc --noEmit     # must be silent
npm test             # 18 passed
```

### Step 3 — Tools mode (the demo mode)

```bash
npm run dev
```

Note the port — Next falls back to **3001** if 3000 is busy, and the URL you
rehearsed on will 404. Open it, then run turns 1–5 from §8.

**What proves it works:**

| Check | Expected |
|---|---|
| Server banner | `mode=tools  mcp=true  extraction=gpt-5.4-mini` |
| Tool count | `tools=5  db=[get-schema, list-gds-procedures, read-cypher]` |
| Memory Panel | **Visible** above each answer, with recent / observations / reasoning chips |
| Reasoning Trace | `query_memory → answer → store_memory` |
| Per-turn log | `Done \| steps=N queries=1 stores=N` |

`stores=0` is fine — look for `store_memory skipped by model — persisted turn in
onFinish` right after it. Nothing is lost.

### Step 4 — Provider mode (transparent)

Stop the server, then:

```bash
NAMS_MODE=provider npm run dev
```

Ask **"What do you remember about me?"** — same user, no re-seeding needed; all three
modes share one memory store.

**Verified reply:** *"You're Priya, a graph data engineer at Acme Analytics in
Bangalore. You prefer concise, technical answers and mostly work in Python."*

| Check | Expected |
|---|---|
| Banner | `mode=provider` |
| Log | `Done \| steps=1 queries=0 stores=0` |
| Memory Panel | **Gone** — and that is the point |

`queries=0 stores=0` with a correct answer is the whole transparent-mode argument on
one line: memory happened, and nothing was rendered. Say that out loud if you show
this mode.

Database questions still work here — MCP attaches separately (`tools=3`, no memory
tools). Verified: *"There are **46,088 Organization nodes**"*, `steps=3`.

### Step 5 — Middleware mode

```bash
NAMS_MODE=middleware npm run dev
```

Ask **"Which programming language do I prefer and where am I based?"**

**Verified reply:** *"You prefer **Python**, and you're based in **Bangalore**."*
— `mode=middleware`, `steps=1 queries=0 stores=0`, `tools=3`.

Observably identical to provider mode. The difference is *where* memory attached:
`wrap()` decorates an already-resolved model instead of a provider — for apps whose
models come from a registry or per-tenant config rather than `openai(...)`.

### Step 6 — Reset to demo config

```bash
grep -n NAMS_MODE .env    # must read NAMS_MODE=tools before you present
```

`NAMS_MODE` from the shell overrides `.env`, so a leftover `NAMS_MODE=provider` in
your terminal history is the easiest way to start the talk with no Memory Panel.
Start the demo in a **fresh terminal**.

### The one-line story across modes

Same question, same memory, same store — three different seams:

| Mode | steps | queries | Panel | What it demonstrates |
|---|---|---|---|---|
| tools | 3 | 1 | **visible** | The memory cycle, rendered |
| provider | 1 | 0 | hidden | Guaranteed memory, zero ceremony |
| middleware | 1 | 0 | hidden | Same, on a model you already have |
