# Vercel AI SDK + Neo4j — Node.js Scripts

Step-by-step agent examples using the [Vercel AI SDK](https://sdk.vercel.ai) with Neo4j.

## Scripts

| File | Description |
|------|-------------|
| `0-direct-query.mjs` | Direct Neo4j query — sanity check, no AI |
| `1-mcp-agent.mjs` | MCP agent — connects to a Neo4j MCP server via `createMCPClient` |
| `2-custom-tools-agent.mjs` | MCP + custom Cypher tools merged in one agent |
| `3-memory-agent.mjs` | Memory with the low-level `@neo4j-labs/agent-memory` client — you write the before/after hooks |
| `4-nams-provider-agent.mjs` | Memory with `@neo4j-labs/nams-ai-provider` — provider / middleware / tools modes, same as the Next.js demo |
| `mcp.mjs` | Shared MCP connection + auth helper (mirrors the demo's `lib/neo4j-mcp.ts`) |
| `prompts.mjs` | Shared system prompts (mirrors the demo's `lib/constants.ts`) |
| `providers.mjs` | Shared LLM provider config (OpenAI / Gemini / Anthropic / Mistral) |

## Setup

```bash
cd notebook
cp .env.example .env   # fill in OPENAI_API_KEY, NEO4J_*, MCP_*, and MEMORY_API_KEY
npm install
```

> **Note:** `@neo4j-labs/nams-ai-provider@0.1.0` declares a peer dependency on
> `zod@~3.0.0`, which is narrower than the `zod@^3.25.x` this project (and the
> rest of the AI SDK) actually uses. The package works correctly with 3.25.x
> in practice, so the included `.npmrc` sets `legacy-peer-deps=true` to keep
> plain `npm install` working — no extra flags needed.

## Running

```bash
node 0-direct-query.mjs             # verify Neo4j connection
node 1-mcp-agent.mjs                # requires MCP_URL/MCP_PORT + MCP auth
node 2-custom-tools-agent.mjs
node 3-memory-agent.mjs             # requires MEMORY_API_KEY
node 4-nams-provider-agent.mjs      # NAMS_MODE=provider (default)

NAMS_MODE=tools node 4-nams-provider-agent.mjs        # model-driven memory tools
NAMS_MODE=middleware node 4-nams-provider-agent.mjs   # transparent memory on a model instance
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | ✅ | LLM API key (or the key matching `AI_PROVIDER`) |
| `AI_PROVIDER` | optional | `openai` (default), `google`, `anthropic`, `mistral` |
| `AI_MODEL` | optional | Overrides the provider default (`gpt-4o-mini` for OpenAI) |
| `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | for scripts 0 & 2 | Direct driver connection |
| `MCP_URL` | for scripts 1–4 | Hosted MCP endpoint (or use `MCP_PORT` for a local server) |
| `MCP_PORT` | optional | Local `neo4j-mcp-server` port → `http://localhost:${MCP_PORT}/mcp` |
| `MCP_BEARER_TOKEN` | one of these | MCP auth via `Authorization: Bearer` — takes precedence |
| `MCP_NEO4J_USERNAME` / `MCP_NEO4J_PASSWORD` | one of these | MCP auth via `Authorization: Basic`; falls back to `NEO4J_USERNAME` / `NEO4J_PASSWORD` |
| `MEMORY_API_KEY` | for scripts 3 & 4 | NAMS key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| `MEMORY_WORKSPACE_ID` | optional | Pin to a specific NAMS workspace; blank uses the key's default |
| `MEMORY_ENDPOINT` | optional | Override the NAMS endpoint |
| `DEMO_USER_ID` | optional | Memory scope — memories persist per user id across runs |
| `NAMS_MODE` | optional | `provider` (default), `middleware`, or `tools` — script 4 only |

## MCP Authentication

`mcp.mjs` picks the scheme from the env vars, exactly like the demo's
`lib/neo4j-mcp.ts`:

| Server | Set |
|--------|-----|
| Hosted Aura / NeoCompanion (OAuth 2.1) | `MCP_BEARER_TOKEN` |
| Self-hosted `mcp-neo4j-cypher` behind Basic auth | `MCP_NEO4J_USERNAME` + `MCP_NEO4J_PASSWORD` |

On a 401 the scripts re-probe the endpoint and report its `WWW-Authenticate`
challenge, so a Basic/Bearer mismatch says so instead of surfacing a bare
`MCP HTTP Transport Error`.

## NAMS Integration Modes (script 4)

| `NAMS_MODE` | API | Behaviour |
|-------------|-----|-----------|
| `provider` (default) | `createNamsProvider({ baseProvider, scope }).languageModel(id)` | Memory retrieved and injected before each call, turn persisted after. No memory tools exposed to the model. |
| `middleware` | `createNams(cfg).wrap(model, scope)` | Same transparent memory, applied to an already-resolved model instance. |
| `tools` | `createNams(cfg).toolsWithMcp(scope, mcpConfig)` | `query_memory` / `store_memory` as tool calls, merged with MCP tools. `enforceQueryMemory()` guarantees the query runs before the answer. |

## LLM Providers

All scripts import from `providers.mjs` — `getModel()` for a model instance,
`getProvider()` for the provider factory that NAMS provider mode needs. Switch
providers via `AI_PROVIDER`:

| Provider | `AI_PROVIDER` | API Key Variable |
|----------|--------------|-----------------|
| OpenAI (default) | `openai` | `OPENAI_API_KEY` |
| Google Gemini | `google` | `GOOGLE_GENERATIVE_AI_API_KEY` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |

## Notes

- AI SDK v6 replaced `maxSteps` with `stopWhen: stepCountIs(N)` — all scripts use the new API. v7 renames it to `isStepCount` but keeps `stepCountIs` as a literal alias (same function object), so no change was needed
- On AI SDK v7, `tool()` takes three type parameters (`tool<INPUT, OUTPUT, CONTEXT>`). These scripts are plain JS and pass no explicit generics, so inference from `inputSchema` still works. In TypeScript, an explicit two-argument `tool<In, Out>` now binds to the `tool<INPUT, CONTEXT>` overload and infers `OUTPUT = never` — it surfaces as `not assignable to type 'undefined'` on `execute`, not as an arity error. Add the third parameter or drop the generics
- MCP uses `createMCPClient` from `@ai-sdk/mcp` (stable API, replaces `experimental_createMCPClient`)
- `workspaceId` belongs on the `MemoryClient` config (sent as `X-Workspace-Id`), not on `createConversation()`, which only accepts `{ userId, metadata }`
- Script 4 records each agent step via `client.reasoning.recordStep`, so past reasoning is recallable in later sessions — the same trace the demo's reasoning panel renders
