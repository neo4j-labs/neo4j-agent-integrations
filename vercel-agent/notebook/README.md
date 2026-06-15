# Vercel AI SDK + Neo4j — Node.js Scripts

Step-by-step agent examples using the [Vercel AI SDK](https://sdk.vercel.ai) with Neo4j.

## Scripts

| File | Description |
|------|-------------|
| `0-direct-query.mjs` | Direct Neo4j query — sanity check, no AI |
| `1-mcp-agent.mjs` | MCP agent — connects to `neo4j-mcp-server` via `createMCPClient` |
| `2-custom-tools-agent.mjs` | MCP + custom Cypher tools merged in one agent |
| `3-memory-agent.mjs` | Memory agent using `@neo4j-labs/agent-memory` |
| `providers.mjs` | Shared LLM provider config (OpenAI / Gemini / Anthropic / Mistral) |

## Setup

```bash
cd notebook
cp .env.example .env   # fill in OPENAI_API_KEY, NEO4J_*, and optionally MEMORY_API_KEY
npm install
```

## Running

```bash
node 0-direct-query.mjs      # verify Neo4j connection
node 1-mcp-agent.mjs         # requires MCP_URL (neo4j-mcp-server)
node 2-custom-tools-agent.mjs
node 3-memory-agent.mjs      # requires MEMORY_API_KEY from memory.neo4jlabs.com
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `NEO4J_URI` | ✅ | Neo4j connection URI |
| `NEO4J_USERNAME` | ✅ | Neo4j username |
| `NEO4J_PASSWORD` | ✅ | Neo4j password |
| `NEO4J_DATABASE` | ✅ | Neo4j database name |
| `MCP_URL` | for scripts 1 & 2 | URL of the `neo4j-mcp-server` HTTP endpoint |
| `MEMORY_API_KEY` | for script 3 | NAMS key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| `AI_PROVIDER` | optional | `openai` (default), `google`, `anthropic`, `mistral` |

## LLM Providers

All scripts import `getModel()` from `providers.mjs`. Switch providers via `AI_PROVIDER`:

| Provider | `AI_PROVIDER` | API Key Variable |
|----------|--------------|-----------------|
| OpenAI (default) | `openai` | `OPENAI_API_KEY` |
| Google Gemini | `google` | `GOOGLE_GENERATIVE_AI_API_KEY` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |

## Notes

- AI SDK v6 replaced `maxSteps` with `stopWhen: stepCountIs(N)` — all scripts use the new API
- MCP uses `createMCPClient` from `@ai-sdk/mcp` (stable API, replaces `experimental_createMCPClient`)
- Memory uses `@neo4j-labs/agent-memory` TypeScript SDK
