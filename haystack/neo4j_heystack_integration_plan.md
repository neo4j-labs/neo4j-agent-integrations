# Neo4j × Haystack 3.0 Integration — Implementation Plan

## Overview

Haystack 3.0 shifted its architecture toward agent-centric design, introducing first-class **Skills** (progressive tool discovery), a **Hooks** system (lifecycle middleware for the agent loop), **built-in introspection** (token/step tracking), **native async execution**, and pre-configured **Agent Pack** agents.

This plan proposes contributing a Neo4j integration into that ecosystem: a Neo4j-backed MCP server, a pre-configured Haystack Agent built on top of it (`Neo4jGraphAgent`), domain-specific tooling, and graph-native agent memory (NAMS). The integration is designed to touch every major new Haystack 3.0 capability, giving a complete, demo-ready reference implementation.

**Goal:** A user points the agent at any Neo4j database and asks questions in plain language — no manual pipeline wiring, no assumptions about what indexes exist.

---

## Phase 1: Neo4j MCP Server ↔ Haystack Agent Connection

**Purpose:** Prove the plumbing before adding any retrieval intelligence.

- Stand up `neo4j-mcp-server` — schema introspection + raw Cypher execution (deliberately the plain server, not GraphRAG)
- Choose transport: stdio for local dev, SSE/HTTP for production (served via Hayhooks)
- Connect a basic Haystack `Agent` to the server using Haystack's native MCP tool support
- Verify end-to-end: Agent discovers schema, runs a Cypher query through the MCP tool, gets a result back

**Deliverable:** Working Agent ↔ MCP ↔ Neo4j round trip. No retrieval logic yet — plumbing only.

**Estimate:** 1–1.5 weeks

---

## Phase 2: neo4j-graphrag Retriever Integration

**Purpose:** This is where GraphRAG behavior actually lives — in the Agent's reasoning over which retrieval tool to use, not in a single built-in method.

- Use `neo4j-graphrag` Python retrievers (same set as `neo4j_graphrag_haystack.ipynb`) and expose them as Agent tools:
  - `VectorRetriever` (semantic search)
  - `VectorCypherRetriever` (semantic search + graph traversal enrichment)
  - `HybridRetriever` (vector + fulltext)
  - `HybridCypherRetriever` (hybrid retrieval + graph traversal enrichment)
- Attach these tools to the same Agent from Phase 1, alongside the Phase 1 Cypher/schema tools
- **Schema-aware fallback handling** (see Edge Case section below): tool availability is filtered based on what indexes actually exist in the connected DB
- Wrap tools behind `SkillToolset` for progressive discovery — the **Skills** coverage
- Run the Agent in async mode — MCP calls and the Neo4j driver both support this natively — the **Async** coverage
- Package as a pre-configured Agent (`Neo4jGraphAgent`), matching the Agent Pack convention (comparable to the existing `deep-research` / `advanced-rag` agents)

**Deliverable:** `Neo4jGraphAgent` — a regular Haystack `Agent`, pre-wired with schema-aware Neo4j retrieval tools, doing real graph-aware retrieval against any connected DB.

**Estimate:** 1.5–2 weeks

---

## Phase 3: Custom Tools + Hooks

**Purpose:** Move from demo-grade to production-grade.

- Add domain-specific composite tools on top of the raw MCP tools (e.g. "find related entities within N hops," or business-logic-specific queries)
- Add a `before_tool` hook gating Cypher-writing tools before execution, using Haystack's existing hook system (e.g. `ConfirmationHook` or a custom equivalent) — the **Hooks** coverage
- Optional: hook-gated auto-index creation (see Edge Case section)

**Deliverable:** Agent is guarded against unsafe/expensive write operations; extensible with client-specific tools.

**Estimate:** 1 week

---

## Phase 4: NAMS — Neo4j Agent Memory

**Purpose:** Replace Haystack's default in-process memory with persistent, relationship-aware memory.

- Add `mcp-neo4j-agent-memory` (or `neo4j-labs/agent-memory`) as an additional MCP server, or wire `Neo4jMemoryStore` directly into the Agent's memory slot
- Conversation history and entity relationships persist in the graph across sessions, not just in-process

**Deliverable:** Agent retains context and entity relationships across sessions/restarts.

**Estimate:** 1–1.5 weeks

---

## Edge Case: Missing Vector / Fulltext Index

Handled by schema discovery (start of Phase 2), so the agent is never blind:

1. On connect, schema discovery checks for existing vector indexes, fulltext indexes, and graph structure
2. Tool availability is filtered accordingly:
  - No vector index → `VectorRetriever` / `VectorCypherRetriever` unavailable
  - No fulltext index → `HybridRetriever` / `HybridCypherRetriever` unavailable
  - Raw Cypher traversal via the Phase 1 MCP tools **always works** (schema-only dependency)
3. Agent falls back to raw Cypher traversal when no indexes exist; if a vector index exists without fulltext, it still uses `VectorCypherRetriever`
4. Optional (Phase 3, hook-gated): agent offers to create the missing index (`CREATE VECTOR INDEX ...`) with user confirmation

This graceful degradation is itself a pitch point — the integration adapts to whatever state a real customer's DB is in.

---

## Feature Coverage vs. Haystack 3.0

| Haystack 3.0 Feature | Covered In |
|---|---|
| Skills (`SkillToolset`) | Phase 2 |
| Async pipeline/agent execution | Phase 2 |
| Pre-built Agent pattern (Agent Pack style) | Phase 2 |
| Custom tools | Phase 3 |
| Hooks (`before_tool`) | Phase 3 |
| Agent memory | Phase 4 |
| Built-in introspection (token/step tracking) | Native — inherited automatically from Haystack's `Agent`, no extra work needed |

---

## Overall Timeline

| Phase | Estimate |
|---|---|
| Phase 1 — MCP server ↔ Agent connection | 1–1.5 weeks |
| Phase 2 — GraphRAG retriever integration | 1.5–2 weeks |
| Phase 3 — Custom tools + hooks | 1 week |
| Phase 4 — NAMS memory | 1–1.5 weeks |
| Testing, docs, demo prep | 0.5–1 week |
| **Total** | **5.5–7 weeks** |

Each phase is independently demoable — a working MCP server alone (Phase 1) is already a useful, standalone artifact outside of Haystack, so client-facing progress can be shown incrementally rather than only at final delivery.

---

## Demo Target

*"Point it at any Neo4j DB, ask a question in plain English, get a grounded answer with graph context — zero pipeline config, and it adapts automatically to whatever indexes the DB already has."*
