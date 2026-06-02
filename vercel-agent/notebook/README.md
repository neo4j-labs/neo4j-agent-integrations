# Vercel AI SDK + Neo4j Integration

## Overview

**[Vercel AI SDK](https://sdk.vercel.ai)** is a TypeScript-first, provider-agnostic toolkit for building AI-powered applications and agents. It supports streaming, structured output, and multi-step agentic tool loops with a unified interface across OpenAI, Google Gemini, Anthropic, Mistral, and more.

**Key Features:**
- `generateText` / `streamText` for one-shot and streaming LLM calls
- Multi-step agentic loops via `stopWhen: stepCountIs(N)` (AI SDK v6+)
- `tool()` helper with `jsonSchema()` for type-safe tool definitions (no Zod required)
- Provider-agnostic — swap LLMs with a single environment variable change
- MCP client support via `createMCPClient` from `@ai-sdk/mcp`

**Official Resources:**
- Website: [sdk.vercel.ai](https://sdk.vercel.ai)
- Documentation: [sdk.vercel.ai/docs](https://sdk.vercel.ai/docs)
- MCP client docs: [sdk.vercel.ai/docs/ai-sdk-core/mcp-clients](https://sdk.vercel.ai/docs/ai-sdk-core/mcp-clients)

## Repository Structure

```
vercel-agent/
  notebook/    ← Node.js scripts and Jupyter notebook (agents, MCP, memory demos)
  README.md    ← This file
```

### `notebook/` — Node.js Scripts & Jupyter Notebook

Step-by-step agent examples you can run directly with `node` or via the Jupyter notebook:

| File | Description |
|------|-------------|
| `0-direct-query.mjs` | Direct Neo4j query — sanity check, no AI |
| `1-mcp-agent.mjs`    | MCP agent — connects to `neo4j-mcp-server` |
| `2-custom-tools-agent.mjs` | MCP + custom Cypher tools merged |
| `3-memory-agent.mjs` | Memory agent using `@neo4j-labs/agent-memory` |
| `providers.mjs`      | Shared LLM provider config (OpenAI / Gemini / Anthropic / Mistral) |
| [`vercel_agent.ipynb`](notebook/vercel_agent.ipynb) | Jupyter setup notebook — credentials, MCP server start |
| [`vercel_agent.html`](https://htmlpreview.github.io/?https://raw.githubusercontent.com/karanchellani/neo4j-agent-integrations/vercel-agent/vercel-agent/notebook/vercel_agent.html) | Observable notebook — interactive browser demo |

```bash
cd notebook
cp .env.example .env   # fill in OPENAI_API_KEY, NEO4J_*, MEMORY_API_KEY
npm install
node 0-direct-query.mjs   # verify Neo4j connection
node 1-mcp-agent.mjs      # requires MCP server (see notebook for setup)
node 3-memory-agent.mjs   # requires MEMORY_API_KEY from memory.neo4jlabs.com
```

## Architecture

![Architecture](https://mermaid.ink/img/Z3JhcGggVEQKICAgIFVzZXIoWyJOb3RlYm9vayAvIEFwcCJdKSAtLT4gZ2VuCgogICAgc3ViZ3JhcGggc2RrWyJWZXJjZWwgQUkgU0RLIl0KICAgICAgICBnZW5bImdlbmVyYXRlVGV4dCgpIl0KICAgIGVuZAoKICAgIGdlbiAtLT4gcDFbIjEuIE1DUCBBZ2VudApAYWktc2RrL21jcCJdCiAgICBnZW4gLS0-IHAyWyIyLiBDdXN0b20gVG9vbHMKdG9vbCgpICsgbmVvNGotZHJpdmVyIl0KICAgIGdlbiAtLT4gcDNbIjMuIE1lbW9yeSBBZ2VudApAbmVvNGotbGFicy9hZ2VudC1tZW1vcnkiXQoKICAgIHAxIC0tPnxIVFRQIEJhc2ljIEF1dGh8IG1jcFsibmVvNGotbWNwLXNlcnZlciJdCiAgICBwMiAtLT4gZGJbKCJOZW80agpHcmFwaCBEQiIpXQogICAgcDMgLS0-IG5hbXNbKCJOQU1TCm1lbW9yeS5uZW80amxhYnMuY29tIildCiAgICBtY3AgLS0-IGRi)


## Extension Points

### 1. MCP Integration

The Vercel AI SDK supports MCP via the `@ai-sdk/mcp` package. Use `createMCPClient` (stable API) to connect to any MCP server over HTTP transport; `mcpClient.tools()` returns a tools object ready for `generateText`.

```bash
cd notebook && npm install
```

```js
import { generateText, stepCountIs } from 'ai';
import { createMCPClient } from '@ai-sdk/mcp';

// MCP_URL: hosted remote server or local (default: http://localhost:8443/mcp)
const mcpUrl = process.env.MCP_URL || `http://localhost:${process.env.MCP_PORT || '8443'}/mcp`;
const creds  = Buffer.from(`${process.env.NEO4J_USERNAME}:${process.env.NEO4J_PASSWORD}`)
  .toString('base64');

const mcpClient = await createMCPClient({
  transport: {
    type:    'http',
    url:     mcpUrl,
    headers: { Authorization: `Basic ${creds}` },
  },
});

const mcpTools = await mcpClient.tools();  // get-schema, read-cypher, write-cypher, ...

const { text, steps } = await generateText({
  model,
  system:   'You are a graph database assistant. Run get-schema first if unfamiliar.',
  prompt:   'How many organizations are in the database?',
  tools:    mcpTools,
  stopWhen: stepCountIs(10),
});

await mcpClient.close();
```

**Example output:**
```
Connected to Neo4j MCP ✓
Available tools: get-schema, list-gds-procedures, read-cypher, write-cypher

Query: How many organizations are in the database?

Result: There are 46,088 organizations in the database.
[Completed in 3 step(s)]
```

**When to use:** Start here. Covers most graph queries with zero Cypher knowledge required — the agent uses `get-schema` + `read-cypher` autonomously.

---

### 2. Direct Neo4j Integration

For queries that need hand-tuned Cypher or access patterns the MCP server doesn't expose, use the `neo4j-driver` directly. Custom tools are defined with `tool()` + `jsonSchema()` and can be **merged with MCP tools** in the same `generateText` call.

```js
import { generateText, tool, jsonSchema, stepCountIs } from 'ai';
import neo4j from 'neo4j-driver';

const driver = neo4j.driver(
  process.env.NEO4J_URI,
  neo4j.auth.basic(process.env.NEO4J_USERNAME, process.env.NEO4J_PASSWORD),
  { disableLosslessIntegers: true }
);

const getInvestments = tool({
  description: 'Returns investments made by a company.',
  inputSchema: jsonSchema({
    type: 'object',
    properties: {
      company: { type: 'string', description: 'Company or organization name' },
    },
    required: ['company'],
  }),
  execute: async ({ company }) => {
    const { records } = await driver.executeQuery(
      `MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
       WHERE o.name = $company
       RETURN i.id AS id, i.name AS name, head(labels(i)) AS type`,
      { company },
      { database: process.env.NEO4J_DATABASE }
    );
    return records.map(r => r.toObject());
  },
});

// Merge custom tool with MCP tools — the framework routes each call automatically
const { text } = await generateText({
  model,
  prompt:   'Which companies did Google invest in?',
  tools:    { ...mcpTools, getInvestments },
  stopWhen: stepCountIs(10),
});

await driver.close();
```

**When to use:** When you need precise Cypher beyond what the MCP server provides, or want to mix domain-specific tools with MCP tools in a single agent.

---

### 3. Persistent Memory via `@neo4j-labs/agent-memory`

Memory is managed by the [Neo4j Agent Memory Service (NAMS)](https://memory.neo4jlabs.com) via the official `@neo4j-labs/agent-memory` TypeScript client. No separate Neo4j instance required — just a free API key.

**Memory is split into two tiers:**
- **Short-term** — conversation messages, reflections, observations (scoped per session)
- **Long-term** — named entities (concepts, facts, research findings) searchable across sessions

```js
import { generateText, stepCountIs } from 'ai';
import { MemoryClient } from '@neo4j-labs/agent-memory';

const memoryClient = new MemoryClient({ apiKey: process.env.MEMORY_API_KEY });

// Create a new conversation session
const conv = await memoryClient.shortTerm.createConversation({ userId: 'my-agent' });

// BEFORE query: inject relevant context into system prompt
const ctx      = await memoryClient.shortTerm.getContext(conv.id);
const entities = await memoryClient.longTerm.searchEntities(userQuery, { limit: 5 });

const { text } = await generateText({
  model,
  system: buildSystemWithContext(ctx, entities),
  prompt: userQuery,
  tools:  mcpTools,
  stopWhen: stepCountIs(10),
});

// AFTER query: persist messages and save key findings
await memoryClient.shortTerm.addMessage(conv.id, 'user',      userQuery);
await memoryClient.shortTerm.addMessage(conv.id, 'assistant', text);
await memoryClient.longTerm.addEntity('Research: Google', 'concept', { description: text.slice(0, 500) });
```

**Example output (two-turn demo):**
```
Memory session: conv_abc123
Connected to Neo4j MCP ✓

[USER]: I am conducting a competitive analysis of 'Google'. Tell me about their presence.
 ↳ Injecting context: 0 messages, 0 entities.
[AGENT]: Google appears 1,284 times in the knowledge graph...
 [Memory] Interaction saved to NAMS ✓

[USER]: Based on our conversation, what subsidiaries appear in the database?
 ↳ Injecting context: 2 messages, 1 entity.
[AGENT]: Based on our earlier analysis of Google, the subsidiaries include...
```

**When to use:** Multi-session agents that need to remember past queries, user context, or analysis state across runs. Requires `MEMORY_API_KEY` from [memory.neo4jlabs.com](https://memory.neo4jlabs.com).

---

### 4. NAMS — Hosted Agent Memory

[NAMS (Neo4j Agent Memory Service)](https://neo4j.com/docs/agent-memory/) is a **managed, graph-native REST service** that gives AI agents persistent memory across conversations — no database to run or maintain. It provides three interconnected memory layers stored in a single hosted knowledge graph:

| Layer | What it stores |
|-------|---------------|
| **Short-term** | Conversation history and session state; supports semantic search |
| **Long-term** | Extracted facts, user preferences, and entities (Person, Org, Location, …) across sessions |
| **Reasoning** | Tool-use traces and decision records for future self-improvement |

Get an API key at the [NAMS console](https://console.neo4j.io/agent-memory), then:

```bash
npm install @neo4j-labs/agent-memory
```

```js
import { MemoryClient } from '@neo4j-labs/agent-memory';
import { generateText, stepCountIs } from 'ai';

const memory = new MemoryClient({
  endpoint: 'https://memory.neo4jlabs.com/v1',
  apiKey:   process.env.MEMORY_API_KEY,
});

// Create (or resume) a conversation scoped to this user
const { id: conversationId } = await memory.shortTerm.createConversation({ userId: 'user-123' });

async function runWithMemory(query) {
  // BEFORE: inject short-term context + semantic matches into system prompt
  const ctx     = await memory.shortTerm.getContext(conversationId);
  const matches = await memory.shortTerm.searchMessages(query, {
    sessionId: conversationId, limit: 5, threshold: 0.75,
  });
  const injected = [
    ...matches.map(m  => `[relevant] ${m.content}`),
    ...ctx.reflections.map(r => `[reflection] ${r.content}`),
    ...[...ctx.recentMessages].reverse().slice(-8)
      .map(m => `${m.role.toUpperCase()}: ${m.content}`),
  ].join('\n');

  const { text } = await generateText({
    model,
    system:   injected ? `${BASE_SYSTEM_PROMPT}\n\n${injected}` : BASE_SYSTEM_PROMPT,
    prompt:   query,
    tools:    mcpTools,
    stopWhen: stepCountIs(10),
  });

  // AFTER: persist the exchange
  await memory.shortTerm.addMessage(conversationId, 'user',      query);
  await memory.shortTerm.addMessage(conversationId, 'assistant', text);
  return text;
}
```

**Transports:** The SDK defaults to REST with `MEMORY_API_KEY`. You can also connect via the NAMS MCP endpoint using Basic auth and provide `NEO4J_USERNAME` / `NEO4J_PASSWORD`.

**Full example:** [`vercel_agent_demo/`](vercel_agent_demo/) — a Next.js chat UI wired to NAMS, with Neo4j graph-query tools, session management, and support for both SDK and MCP transports. **This is a local demo only — see the [Chat App Demo](#chat-app-demo-local-only) section below.**

**When to use:** Conversational agents that need out-of-the-box personalization, entity tracking, and reasoning traces across sessions — without managing your own Neo4j instance.

---

---

## Chat App Demo (Local Only)

> **This is boilerplate demo code.**
> Run it locally to explore.

[`vercel_agent_demo/`](vercel_agent_demo/) is a minimal Next.js chat UI that wires together Neo4j MCP tools and NAMS memory into a browser-based chat interface. Its purpose is to show — concretely and interactively — how the agent patterns from the `notebook/` scripts translate to a real UI.

**What it is:**
- A local-only reference implementation / starting point
- A Next.js App Router project you run with `npm run dev`
- Pre-wired to the same `.env` variables used by the notebook scripts

**To run locally:**

```bash
cd vercel_agent_demo
cp ../.env .env.local   # reuse the same env vars
npm install
npm run dev             # starts at http://localhost:3000
```

> If you want to build on top of this, treat it as a starting point and add authentication, error boundaries, and rate limiting before any public deployment.

---

## MCP Authentication

✅ **HTTP Headers (HTTP transport)** — Pass credentials via the `headers` parameter of `createMCPClient`. Used to authenticate per-request against `neo4j-mcp-server` running in HTTP mode.

```js
const creds = Buffer.from(`${NEO4J_USERNAME}:${NEO4J_PASSWORD}`).toString('base64');

const mcpClient = await createMCPClient({
  transport: {
    type:    'http',
    url:     process.env.MCP_URL || 'http://localhost:8443/mcp',
    headers: { Authorization: `Basic ${creds}` },
  },
});
```

> **Important:** Do **not** export `NEO4J_USERNAME` / `NEO4J_PASSWORD` as environment variables when running `neo4j-mcp-server` in HTTP mode — the server will pick them up for its own connection and the per-request auth will not work correctly. Pass credentials only via the `Authorization` header.

## LLM Provider Configuration

All agent files import `getModel()` from [`notebook/providers.mjs`](notebook/providers.mjs), which selects the LLM based on `AI_PROVIDER`. No code changes needed to switch providers.

| Provider | `AI_PROVIDER` | API Key Variable | Extra install |
|----------|--------------|-----------------|---------------|
| **OpenAI** (default) | `openai` | `OPENAI_API_KEY` | — |
| **Google Gemini** | `google` | `GOOGLE_GENERATIVE_AI_API_KEY` | `npm install @ai-sdk/google` |
| **Anthropic Claude** | `anthropic` | `ANTHROPIC_API_KEY` | `npm install @ai-sdk/anthropic` |
| **Mistral** | `mistral` | `MISTRAL_API_KEY` | `npm install @ai-sdk/mistral` |

## Challenges and Gaps

| Area | Detail |
|------|--------|
| **JavaScript only** | The Vercel AI SDK has no Python support — all agent code runs in Node.js |
| **`stopWhen` is v6+** | `maxSteps` was silently removed in AI SDK v6; passing it does nothing. Use `stopWhen: stepCountIs(N)` |
| **MCP transport type** | `neo4j-mcp-server` HTTP mode requires `type: 'http'`, not `type: 'sse'` |
| **Edge runtime** | Neo4j driver needs persistent TCP — incompatible with Vercel edge functions; use Node.js serverless runtime |
| **NAMS API key** | `3-memory-agent.mjs` requires `MEMORY_API_KEY` — get a free key at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |

## Resources

- [Vercel AI SDK Documentation](https://sdk.vercel.ai/docs)
- [Vercel AI SDK — Tool Use](https://sdk.vercel.ai/docs/ai-sdk-core/tools-and-tool-calling)
- [Vercel AI SDK — MCP Clients](https://sdk.vercel.ai/docs/ai-sdk-core/mcp-clients)
- [`@ai-sdk/mcp` on npm](https://www.npmjs.com/package/@ai-sdk/mcp)
- [Neo4j Agent Memory (`@neo4j-labs/agent-memory`)](https://github.com/neo4j-labs/agent-memory)
- [Neo4j MCP Server](https://github.com/neo4j-contrib/mcp-neo4j)
- [Neo4j JavaScript Driver Documentation](https://neo4j.com/docs/javascript-manual/current/)

