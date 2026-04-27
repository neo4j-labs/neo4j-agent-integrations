# Vercel AI SDK + Neo4j Integration

## Overview

**[Vercel AI SDK](https://sdk.vercel.ai)** is a TypeScript-first, provider-agnostic toolkit for building AI-powered applications and agents. It supports streaming, structured output, and multi-step agentic tool loops with a unified interface across OpenAI, Google Gemini, Anthropic, Mistral, and more.

**Key Features:**
- `generateText` / `streamText` for one-shot and streaming LLM calls
- Multi-step agentic loops via `stopWhen: stepCountIs(N)` (AI SDK v6+)
- `tool()` helper with `jsonSchema()` for type-safe tool definitions (no Zod required)
- Provider-agnostic — swap LLMs with a single environment variable change
- MCP client support via `@ai-sdk/mcp`

**Official Resources:**
- Website: [sdk.vercel.ai](https://sdk.vercel.ai)
- Documentation: [sdk.vercel.ai/docs](https://sdk.vercel.ai/docs)
- MCP client docs: [sdk.vercel.ai/docs/ai-sdk-core/mcp-clients](https://sdk.vercel.ai/docs/ai-sdk-core/mcp-clients)

## Examples

| File | Description |
|------|-------------|
| [vercel_agent.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/vercel-agent/vercel_agent.ipynb) | Notebook walkthrough of all three integration patterns |

## Extension Points

### 1. MCP Integration

The Vercel AI SDK supports MCP via the `@ai-sdk/mcp` package. The `experimental_createMCPClient` function connects to any MCP server over HTTP or SSE transport, and `mcpClient.tools()` returns a tools object ready for `generateText`.

```bash
npm install @ai-sdk/mcp
```

```js
import { generateText, stepCountIs } from 'ai';
import { experimental_createMCPClient } from '@ai-sdk/mcp';

// Credentials passed per-request via Basic Auth header
const creds = Buffer.from(`${process.env.NEO4J_USERNAME}:${process.env.NEO4J_PASSWORD}`)
  .toString('base64');

const mcpClient = await experimental_createMCPClient({
  transport: {
    type:    'http',
    url:     `http://localhost:${process.env.MCP_PORT}/mcp`,
    headers: { Authorization: `Basic ${creds}` },
  },
});

const mcpTools = await mcpClient.tools();  // get-schema, read-cypher, write-cypher, ...

const { text, steps } = await generateText({
  model,
  system:   'You are a graph database assistant. Run get-schema first if unfamiliar.',
  prompt:   'How many organizations are in the database?',
  tools:    mcpTools,
  stopWhen: stepCountIs(10),   // AI SDK v6+ — replaces the removed maxSteps
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

```bash
npm install neo4j-driver
```

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
    const session = driver.session({ database: process.env.NEO4J_DATABASE });
    try {
      const result = await session.run(
        `MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
         WHERE o.name = $company
         RETURN i.id AS id, i.name AS name, head(labels(i)) AS type`,
        { company }
      );
      return result.records.map(r => r.toObject());
    } finally {
      await session.close();
    }
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

**Example output:**
```
Result: Google has made investments in several notable companies:
- Ionic Security
- Avere Systems
- FlexiDAO
- Cloudflare
- Trifacta
[Completed in 4 step(s)]
```

**When to use:** When you need precise Cypher beyond what the MCP server provides, or want to mix domain-specific tools (e.g. custom aggregations, write operations) with MCP tools in a single agent.

---

### 3. Custom Tools / Persistent Memory

The `neo4j-agent-memory` package stores agent knowledge as a graph in Neo4j, enabling cross-session persistence. The pattern wraps `generateText` with two hooks:

- **Before hook** (`injectMemoryContext`) — retrieves relevant memories and injects them into the system prompt
- **After hook** (`saveInteraction`) — saves the interaction to the memory graph for future sessions

```bash
npm install neo4j-agent-memory
```

```js
import { createMemoryService, createMemoryTools } from 'neo4j-agent-memory';

// neo4j-agent-memory bundles driver v5 — use bolt+ssc:// (trust all certs) for AuraDB
const memUri = process.env.MEMORY_NEO4J_URI.replace(/^neo4j(\+s)?:\/\//, 'bolt+ssc://');

const memory = await createMemoryService({
  neo4j: { uri: memUri, username, password, database },
  autoRelate: { enabled: true, minSharedTags: 2 },
});
const memoryTools = createMemoryTools(memory);
// Available: store_skill, store_pattern, store_concept, recall_skills, recall_concepts, recall_patterns

async function runWithMemory(query) {
  // BEFORE: inject relevant memories into system prompt
  const bundle = await memory.retrieveContextBundle({ agentId, prompt: query });
  const ctx = bundle.memories.map(m => `- ${m.content}`).join('\n') || 'None yet.';

  const { text } = await generateText({
    model,
    system: `${SYSTEM_PROMPT}\n\n--- MEMORY CONTEXT ---\n${ctx}\n----------------------`,
    prompt: query,
    tools:  { ...mcpTools, ...memoryTools },
    stopWhen: stepCountIs(10),
  });

  // AFTER: save interaction to memory graph
  await saveInteraction(query, text);
  return text;
}
```

**Example output (two-turn demo):**
```
[USER]: I am conducting a competitive analysis of 'Google'. I am specifically
        worried about their subsidiaries and top-tier competitors in the AI space.
[AGENT]: Understood. I've noted that we're tracking Google for competitive intelligence...
 [Hook] Saving interaction to Neo4j memory graph...

--- Indexing memory (5s)... ---

[USER]: What are the main risks in the supply chain for the company I am currently tracking?
 ↳ Injecting 1 memories into context.
   Memory 1: Conducting competitive analysis of Google — focused on subsidiaries and AI competitors...
[AGENT]: Based on our ongoing analysis of Google, the main supply chain risks include...
```

**When to use:** Multi-session agents that need to remember past queries, user context, or analysis state. Particularly useful for research assistants and monitoring agents.

---

## MCP Authentication

**Supported Mechanisms:**

✅ **HTTP Headers (HTTP transport)** — Pass credentials via the `headers` parameter of `experimental_createMCPClient`. Used to authenticate per-request against `neo4j-mcp-server` running in HTTP mode.

```js
const creds = Buffer.from(`${NEO4J_USERNAME}:${NEO4J_PASSWORD}`).toString('base64');

const mcpClient = await experimental_createMCPClient({
  transport: {
    type:    'http',
    url:     'http://localhost:8443/mcp',
    headers: { Authorization: `Basic ${creds}` },
  },
});
```

> **Important:** Do **not** export `NEO4J_USERNAME` / `NEO4J_PASSWORD` as environment variables when running `neo4j-mcp-server` in HTTP mode — the server will pick them up for its own connection and the per-request auth will not work correctly. Pass credentials only via the `Authorization` header inside your JS code.

## LLM Provider Configuration

All three agent files import `getModel()` from [`providers.mjs`](providers.mjs), which selects the LLM based on the `AI_PROVIDER` environment variable. No code changes are needed to switch providers.

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
| **Memory TLS** | `neo4j-agent-memory` bundles driver v5 — use `bolt+ssc://` for AuraDB/demo servers, not `neo4j+s://` |
| **Edge runtime** | Neo4j driver and `neo4j-agent-memory` need persistent TCP — incompatible with Vercel edge functions; use Node.js serverless runtime |
| **`experimental_createMCPClient`** | Still experimental; API may change in future SDK versions |
| **Separate memory DB** | `neo4j-agent-memory` requires write access — keep it on a separate instance from read-only knowledge graphs |

## Resources

- [Vercel AI SDK Documentation](https://sdk.vercel.ai/docs)
- [Vercel AI SDK — Tool Use](https://sdk.vercel.ai/docs/ai-sdk-core/tools-and-tool-calling)
- [Vercel AI SDK — MCP Clients](https://sdk.vercel.ai/docs/ai-sdk-core/mcp-clients)
- [`@ai-sdk/mcp` on npm](https://www.npmjs.com/package/@ai-sdk/mcp)
- [`neo4j-agent-memory` on npm](https://www.npmjs.com/package/neo4j-agent-memory)
- [Neo4j MCP Server](https://github.com/neo4j-contrib/mcp-neo4j)
- [Neo4j JavaScript Driver Documentation](https://neo4j.com/docs/javascript-manual/current/)
