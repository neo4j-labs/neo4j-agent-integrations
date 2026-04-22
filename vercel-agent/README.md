# Vercel AI SDK + Neo4j Integration

## Overview

The [Vercel AI SDK](https://sdk.vercel.ai) is a TypeScript-first, provider-agnostic toolkit for building AI-powered applications and agents. It supports streaming, structured output, and multi-step agentic tool loops with a unified interface across **OpenAI, Google Gemini, Anthropic, Mistral**, and more.

**Key Features:**
- `generateText` / `streamText` for one-shot and streaming LLM calls
- Multi-step agentic loops via `stopWhen: stepCountIs(N)` (AI SDK v6+)
- `tool()` helper with `jsonSchema()` for type-safe tool definitions (no Zod required)
- Provider-agnostic — swap LLMs with a single env variable change
- MCP client support via `@ai-sdk/mcp`

## File Structure

```
vercel-agent/
├── providers.mjs               # LLM provider config — swap OpenAI/Gemini/Anthropic/Mistral
├── 1-mcp-agent.mjs             # Neo4j MCP integration + basic agent (Sections 2–4)
├── 2-custom-tools-agent.mjs    # Custom Cypher tool combined with MCP tools (Section 5)
├── 3-memory-agent.mjs          # Persistent memory with neo4j-agent-memory (Section 6)
├── .env.example                # Template for all required environment variables
├── package.json                # npm dependencies + run scripts
└── vercel_agent.ipynb          # Notebook walkthrough (sets env vars, runs the .mjs files)
```

## Quick Start

### 1. Install dependencies

```bash
npm install
pip install --ignore-requires-python neo4j-mcp-server
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set your LLM API key and Neo4j credentials
```

### 3. Start the Neo4j MCP server

```bash
neo4j-mcp-server \
  --neo4j-uri          neo4j+s://demo.neo4jlabs.com:7687 \
  --neo4j-database     companies \
  --neo4j-transport-mode http \
  --neo4j-http-port    8443
```

> **Important:** Do **not** export `NEO4J_USERNAME` / `NEO4J_PASSWORD` when running the server in HTTP mode — credentials are passed per-request via the `Authorization: Basic ...` header inside the JS files.

The server exposes four tools:

| Tool | Description |
|------|-------------|
| `get-schema` | Returns the full graph schema |
| `list-gds-procedures` | Lists Graph Data Science procedures |
| `read-cypher` | Executes a read-only Cypher query |
| `write-cypher` | Executes a write Cypher query |

### 4. Run the examples

```bash
# MCP agent — asks "How many organizations are in the database?"
node 1-mcp-agent.mjs
# or: npm run mcp-agent

# Custom tools agent — asks "Which companies did Google invest in?"
node 2-custom-tools-agent.mjs
# or: npm run custom-tools

# Memory agent — two-turn demo with before/after memory hooks
node 3-memory-agent.mjs
# or: npm run memory-agent
```

---

## LLM Provider Configuration

All three agent files import `getModel()` from [`providers.mjs`](providers.mjs), which selects the LLM based on the `AI_PROVIDER` environment variable. No code changes are needed to switch providers.

| Provider | `AI_PROVIDER` | API Key Variable | Extra install |
|----------|--------------|-----------------|---------------|
| **OpenAI** (default) | `openai` | `OPENAI_API_KEY` | — |
| **Google Gemini** | `google` | `GOOGLE_GENERATIVE_AI_API_KEY` | `npm install @ai-sdk/google` |
| **Anthropic Claude** | `anthropic` | `ANTHROPIC_API_KEY` | `npm install @ai-sdk/anthropic` |
| **Mistral** | `mistral` | `MISTRAL_API_KEY` | `npm install @ai-sdk/mistral` |

```bash
# Example: switch to Google Gemini
export AI_PROVIDER=google
export AI_MODEL=gemini-2.0-flash
export GOOGLE_GENERATIVE_AI_API_KEY=your-key
node 1-mcp-agent.mjs
```

---

## File Descriptions

### `providers.mjs`
Exports `getModel()` — reads `AI_PROVIDER` and `AI_MODEL` from the environment and returns the corresponding Vercel AI SDK model instance. Provider packages are loaded lazily, so you only need to install the one you use.

### `1-mcp-agent.mjs`
Connects to the Neo4j MCP server via HTTP transport and runs a multi-step agent query. Demonstrates:
- `experimental_createMCPClient` from `@ai-sdk/mcp` with Basic Auth
- `createAgent()` helper pattern
- `askGraph()` runner with `stopWhen: stepCountIs(10)`

### `2-custom-tools-agent.mjs`
Extends the MCP agent with a hand-written Cypher tool. Demonstrates:
- `tool()` + `inputSchema: jsonSchema({...})` for custom tool definition
- Merging custom tools with MCP tools: `{ ...mcpTools, getInvestments }`
- Direct `neo4j-driver` connection for custom query logic

### `3-memory-agent.mjs`
Adds cross-session persistent memory using `neo4j-agent-memory`. Demonstrates:
- `createMemoryService` / `createMemoryTools` initialisation
- **Before hook** (`injectMemoryContext`): retrieves relevant memories and injects them into the system prompt
- **After hook** (`saveInteraction`): persists the interaction to the memory graph
- Two-turn demo: Turn 2 correctly recalls the research context set in Turn 1

---

## Key API Patterns (AI SDK v6)

### Multi-step agentic loop

```js
import { generateText, stepCountIs } from 'ai';

const { text, steps } = await generateText({
  model,
  system:   'You are a graph database assistant.',
  prompt:   'How many organizations are in the database?',
  tools:    mcpTools,
  stopWhen: stepCountIs(10),   // AI SDK v6 — replaces the removed maxSteps
});
```

### MCP client (HTTP transport)

```js
import { experimental_createMCPClient } from '@ai-sdk/mcp';

const creds = Buffer.from(`${NEO4J_USERNAME}:${NEO4J_PASSWORD}`).toString('base64');

const mcpClient = await experimental_createMCPClient({
  transport: {
    type:    'http',
    url:     'http://localhost:8443/mcp',
    headers: { Authorization: `Basic ${creds}` },
  },
});
const mcpTools = await mcpClient.tools();
await mcpClient.close();
```

### Custom tool with `jsonSchema()`

```js
import { tool, jsonSchema } from 'ai';

const myTool = tool({
  description: 'Fetch data from Neo4j',
  inputSchema: jsonSchema({
    type: 'object',
    properties: {
      keyword: { type: 'string' },
    },
    required: ['keyword'],
  }),
  execute: async ({ keyword }) => { /* Cypher query */ },
});
```

### Agent memory (bolt+ssc:// for AuraDB)

```js
import { createMemoryService, createMemoryTools } from 'neo4j-agent-memory';

// neo4j-agent-memory bundles driver v5 — use bolt+ssc:// (trust all certs)
const memUri = process.env.MEMORY_NEO4J_URI.replace(/^neo4j(\+s)?:\/\//, 'bolt+ssc://');

const memory = await createMemoryService({
  neo4j: { uri: memUri, username, password, database },
  autoRelate: { enabled: true },
});
const memoryTools = createMemoryTools(memory);
// Tools: store_skill, store_pattern, store_concept, recall_skills, recall_concepts, recall_patterns
```

---

## Challenges and Gaps

| Area | Detail |
|------|--------|
| **JavaScript only** | The Vercel AI SDK has no Python support — all agent code runs in Node.js |
| **`stopWhen` is v6+** | `maxSteps` was silently removed in AI SDK v6; passing it does nothing. Use `stopWhen: stepCountIs(N)` |
| **MCP transport** | `neo4j-mcp-server` HTTP mode requires `type: 'http'`, not `type: 'sse'` |
| **Memory TLS** | `neo4j-agent-memory` bundles driver v5 — use `bolt+ssc://` for AuraDB/demo servers |
| **Edge runtime** | Neo4j driver and `neo4j-agent-memory` need persistent TCP — incompatible with Vercel edge functions; use Node.js serverless runtime |
| **`experimental_createMCPClient`** | Still experimental; API may change in future SDK versions |

## Resources

- [Vercel AI SDK Documentation](https://sdk.vercel.ai/docs)
- [Vercel AI SDK — Tool Use](https://sdk.vercel.ai/docs/ai-sdk-core/tools-and-tool-calling)
- [Vercel AI SDK — MCP Clients](https://sdk.vercel.ai/docs/ai-sdk-core/mcp-clients)
- [`@ai-sdk/mcp` on npm](https://www.npmjs.com/package/@ai-sdk/mcp)
- [`neo4j-agent-memory` on npm](https://www.npmjs.com/package/neo4j-agent-memory)
- [Neo4j MCP Server](https://github.com/neo4j-contrib/mcp-neo4j)
- [Neo4j JavaScript Driver Documentation](https://neo4j.com/docs/javascript-manual/current/)
