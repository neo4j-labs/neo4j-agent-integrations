# Neo4j Agent Memory in eve's memory provider registry

Goal: list Neo4j Agent Memory on https://eve.dev/docs/memory next to File
memory, Supermemory, Upstash AgentKit and Kybernesis Arcana.

eve lists only providers that are published on npm and that a maintainer has
agreed to list. So the order is: package, then issue, then registry PR.

## The provider

`namsMemory()` from the `/eve` entry point of `@neo4j-labs/nams-ai-provider`.
It is the same package as the AI SDK provider; the main entry point never loads
eve. This is what [`industry-research-agent/agent/memory/nams.ts`](industry-research-agent/agent/memory/nams.ts)
runs, at version 0.5.0 from npm.

| eve hook | What `namsMemory()` does |
| --- | --- |
| `recall["turn.started"]` | Returns one keyed record (`nams-memory`): notes saved with `remember`, messages from the scope's earlier sessions that match the user's message, NAMS's summaries of those sessions, and matching entities from the scope's knowledge graph. At most `maxMemories` lines (default 8). |
| `capture["turn.completed"]` | Writes the user's message and the final answer to one NAMS conversation per eve session. Tool calls are not saved. NAMS extracts entities and writes summaries from it server-side. |
| `tools()` | `search` (notes, the 10 most recent earlier sessions, and the scope's entities) and `remember` (saves one sentence as a note). Both are plain functions bound to the locked scope; no tool takes a user id. |

Options: `apiKey` (falls back to `MEMORY_API_KEY`), `endpoint`, `workspaceId`,
`logger`, `crossSessionLimit` (3), `maxMemories` (8), `capture` (true),
`tools` (true), `workspaceGraph` (false).

How it meets eve's provider requirements:

- **Partitioning.** Every conversation it creates carries `memory.scope.key` as
  its NAMS `userId`. It lists conversations and searches entities with that
  `userId`, so NAMS filters on the server, and it checks the `userId` again on
  every conversation and entity that comes back. Entities that belong to no
  user are recalled only with `workspaceGraph: true`.
- **Replays.** A replayed recall returns the same record. A replayed capture
  writes nothing, and after a restart the provider compares the conversation's
  newest messages with the turn before it writes.
- **Failures.** A missing API key, or a 401, fails the turn. Any other recall
  error is logged, and the turn gets a record saying memory could not be read.
  A capture error is thrown, and eve logs it after the response.
- **Compatibility.** Optional peer `eve >=0.84.0`: eve 0.84.0 removed
  `defineDurableCallback` and compaction recall, which provider 0.4.0 used
  (0.4.0 covers eve 0.69.0 to 0.83.x). The package's `examples/eve-memory-eval`
  passes on eve 0.84.0 with a mock model and a local fake of NAMS. The range
  does not match prereleases, so npm refuses eve `1.0.0-rc.1` (eve's `latest`
  tag as of 2026-11-02) with `ERESOLVE`. Node 22.23.4 or later.

## Where things stand

| Piece | State |
| --- | --- |
| Provider source | `typescript/packages/vercel-ai-provider/src/vercel-ai-provider-eve.ts` in neo4j-labs/agent-memory. PR #345 was merged on 2026-10-22. |
| npm | Published. `@neo4j-labs/nams-ai-provider` 0.4.0 (2026-10-22) added `/eve`; 0.5.0 (2026-10-27) needs eve 0.84.0 or later. Both need `@neo4j-labs/agent-memory` 0.6.0 (2026-10-22), the SDK release with the hosted-NAMS fixes; the peer range is `~0.6.0`. |
| Checked against hosted NAMS | Yes, on 2026-11-02 with this repo's agent on eve 0.91.0 and provider 0.5.0: `npx eve eval` passes 3/3, including `memory/cross-session-recall`. A fact given in one `eve remote connect --print` session is recalled in the next, both when saved with "Remember this:" and when only stated. |
| eve registry change | Not ready. The draft in `/workspaces/eve` (branch `memory/neo4j-agent-memory`) was written for `@neo4j-labs/agent-memory-eve` and `neo4jMemory()`, an earlier package that was never published. It has to be redone for `@neo4j-labs/nams-ai-provider` and `namsMemory()`. |

## Steps to the PR

1. **Publish** — done: provider 0.5.0 and agent-memory 0.6.0 (see above).
2. **Test on the current eve** — done on eve 0.91.0, the newest stable release
   on 2026-11-02 (`npx eve info`: 0 errors; `npx eve eval`: 3/3). eve 1.0 is in
   release candidates, and the provider's eve peer range would need to accept
   them before a 1.0 project can install it.
3. **Post the issue below** on `vercel/eve` with the Feature request template.
4. **After a maintainer agrees, and at least 2 days after publishing** (eve's
   `minimumReleaseAge`), redo the registry change for `namsMemory()`:
   - registry item `apps/docs/registry/memory/neo4j-agent-memory.ts`, its
     `registry.json` entry (depending on `@neo4j-labs/nams-ai-provider`), the
     catalog entry, the check in `validate-memory-registry.ts`, a gallery
     presentation, and a section and table row in `docs/memory/overview.mdx`,
     plus a changeset;
   - run `pnpm install`, `pnpm --filter eve-docs registry:check`,
     `pnpm docs:check` and `pnpm exec oxfmt --check` on the changed files;
   - commit with both a DCO sign-off and a verified signature
     (`git commit -s -S`): eve rejects commits that lack either;
   - push to your fork and open the PR with the description below.

---

## Issue for vercel/eve (Feature request template)

**Title:** Add Neo4j Agent Memory as a memory provider

**What problem are you trying to solve?**

eve's memory providers today cover a bounded document (File memory), semantic
search (Supermemory, Kybernesis Arcana), and Redis (Upstash AgentKit). None
keeps memory in a graph the application can query. Teams that use Neo4j
currently have to write their own provider.

**Proposed solution**

List `@neo4j-labs/nams-ai-provider` as `memory/neo4j-agent-memory`. Its `/eve`
entry point exports `namsMemory()`, a `defineMemoryProvider` implementation for
the Neo4j Agent Memory Service (NAMS), published from
[neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory/tree/main/typescript/packages/vercel-ai-provider):

- `recall["turn.started"]`: one keyed record with the notes saved for this scope, matching messages and NAMS
  summaries from the scope's earlier sessions, and matching entities from the
  scope's knowledge graph.
- `capture["turn.completed"]`: the user message and the final reply go into one
  NAMS conversation per session. NAMS extracts entities and relationships from
  it in the background and writes the session summaries.
- `tools()`: `search` and `remember`, bound to the locked scope.

How it meets the provider requirements:

- **Partitioning:** conversations are owned by `memory.scope.key`, and the raw
  principal is never sent. Conversation listing and entity search ask NAMS for
  that key only, and the provider checks the key on every result. Entities that
  belong to no user stay out of recall unless `workspaceGraph: true`.
- **Replays:** a replayed recall returns the same record. A replayed capture
  writes nothing, and after a restart the provider checks the conversation's
  newest messages before it writes.
- **Failures:** a missing or rejected key fails the turn. Other recall errors
  degrade to a record saying memory could not be read.
- **Compatibility:** optional peer `eve >=0.84.0`.

```ts title="agent/memory/neo4j-agent-memory.ts"
import { namsMemory } from "@neo4j-labs/nams-ai-provider/eve";
import { defineMemory } from "eve/memory";
import { byPrincipal } from "eve/memory/scope";

export default defineMemory({
  description: "Recall and manage durable context for the current user from Neo4j Agent Memory.",
  provider: namsMemory(), // reads MEMORY_API_KEY
  scope: byPrincipal,
});
```

Validation so far: the package's `examples/eve-memory-eval` runs the provider
inside eve with a mock model and a local fake of NAMS (eve 0.84.0).
Against the hosted service, an eve 0.91.0 agent passes a cross-session recall
eval, where each `t.send()` starts a new session.

If you're happy to list it, I'll open the registry PR once the package has been
on npm for two days.

**Alternatives considered**

- An MCP connection to the service, like `connection/mem0`. It exposes only
  tools: nothing is recalled before a turn or captured after it, and the tools
  are not bound to the caller's scope.
- Leaving it to a custom provider in each app. A registry item makes the Neo4j
  case one command.

---

## PR description for vercel/eve

### Summary

Adds Neo4j Agent Memory to the memory provider registry, as agreed in
#ISSUE_NUMBER. `eve add memory/neo4j-agent-memory` installs
`@neo4j-labs/nams-ai-provider`, declares `MEMORY_API_KEY`, and writes a
principal-scoped `agent/memory/neo4j-agent-memory.ts` slot using `namsMemory()`.

Recall brings back the scope's notes, matching messages and summaries from
earlier sessions, and matching entities from its knowledge graph. Capture saves
each turn; NAMS extracts the graph from it. The memory guide gets a table row
and a section.

### Validation

- `pnpm --filter eve-docs registry:check`
- `pnpm docs:check`
- `pnpm exec oxfmt --check` on the changed files
- Provider: `examples/eve-memory-eval` (eve 0.84.0); cross-session
  recall eval against the hosted service

### Checklist

- [x] This change was requested or approved by a maintainer
- [x] I ran the relevant checks from `CONTRIBUTING.md`
- [x] I added tests and documentation where relevant
- [x] I added a changeset if this touches the published `eve` package
- [x] DCO sign-off passes for every commit (`git commit --signoff`)
