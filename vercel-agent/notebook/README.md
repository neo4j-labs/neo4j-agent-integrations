# Vercel AI SDK + Neo4j — step-by-step scripts

Five small Node.js scripts. Each one adds a single idea, from a plain database query up to an agent that remembers you between runs.

| Script | What it shows |
|---|---|
| `0-direct-query.mjs` | Talk to Neo4j directly. No AI. A quick check that your database login works. |
| `1-mcp-agent.mjs` | An AI agent that queries Neo4j through an MCP server. |
| `2-custom-tools-agent.mjs` | The same agent plus your own hand-written Cypher tools. |
| `3-memory-agent.mjs` | Memory done by hand: load memories before the answer, save the turn after. |
| `4-nams-provider-agent.mjs` | Memory done by the `@neo4j-labs/nams-ai-provider` package, in any of its four modes. |

Shared helpers: `mcp.mjs` (MCP connection), `prompts.mjs` (system prompts), `providers.mjs` (which AI model to use).

---

## Setup

```bash
cd vercel-agent/notebook
cp .env.example .env   # fill in your keys
npm install
```

A plain `npm install` works. If it ever fails with `ERESOLVE`, delete `node_modules/` and `package-lock.json` and install again.

---

## Run

```bash
node 0-direct-query.mjs
node 1-mcp-agent.mjs
node 2-custom-tools-agent.mjs
node 3-memory-agent.mjs
node 4-nams-provider-agent.mjs                     # provider mode (default)

NAMS_MODE=middleware node 4-nams-provider-agent.mjs
NAMS_MODE=tools      node 4-nams-provider-agent.mjs
NAMS_MODE=hooks      node 4-nams-provider-agent.mjs
```

Script 4 asks two questions. The second one ("which company was I researching?") only works if memory recalled the first. Run it again and it still works, because the memory is stored in NAMS, not in the script.

---

## The four memory modes (script 4)

| `NAMS_MODE` | Who takes care of memory |
|---|---|
| `provider` (default) | A wrapper around the AI model adds memories before each answer and saves the turn after. |
| `middleware` | The same wrapper, placed on a model you already have. |
| `tools` | The model itself, by calling `query_memory` and `store_memory`. |
| `hooks` | The script: it loads the saved conversation before each answer and saves every turn after. |

Any other value stops the script with an error.

In every mode the script loads the saved conversation first, like the Next.js demo. It builds its agent once and reuses it, so it passes each question through `prepareCall`:

```js
prepareCall: async ({ options, prompt: _p, messages: _m, ...settings }) => ({
  ...settings,
  messages: [...(await session.loadSession()), { role: 'user', content: options.prompt }],
  runtimeContext: options,               // lets onFinish know what to save
}),
// hooks mode saves the whole turn; tools mode saves only the text; provider and middleware save it themselves
onFinish: async (event) => { await session.onFinish()(event); },

await agent.generate({ prompt: question, options: { prompt: question } });
```

---

## Settings (`.env`)

| Variable | Needed for | What it does |
|---|---|---|
| `OPENAI_API_KEY` | all AI scripts | Your OpenAI key (or the key for `AI_PROVIDER`). |
| `AI_PROVIDER` | optional | `openai` (default), `google`, `anthropic` or `mistral`. |
| `AI_MODEL` | optional | Model to use. Default `gpt-5.4-mini` on OpenAI. |
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | scripts 0 and 2 | Direct database login. |
| `MCP_URL` or `MCP_PORT` | scripts 1–3, optional for 4 | Where the Neo4j MCP server is. |
| `MCP_BEARER_TOKEN`, or `MCP_NEO4J_USERNAME` + `MCP_NEO4J_PASSWORD` | with MCP | Login for the MCP server. A token wins if both are set. |
| `MEMORY_API_KEY` | scripts 3 and 4 | Your NAMS key, free at [memory.neo4jlabs.com](https://memory.neo4jlabs.com). |
| `MEMORY_WORKSPACE_ID` | optional | Use a specific NAMS workspace. |
| `DEMO_USER_ID` | optional | Whose memory to use. Same id = same memories across runs. |
| `NAMS_MODE` | script 4 | `provider`, `middleware`, `tools` or `hooks`. |

**MCP login:** hosted Aura / NeoCompanion servers want a token (`MCP_BEARER_TOKEN`). Self-hosted servers usually want a username and password. On a login error, the scripts tell you which kind the server asked for.

---

## Switching AI providers

Set `AI_PROVIDER` and the matching key. No code changes needed.

| Provider | `AI_PROVIDER` | Key |
|---|---|---|
| OpenAI (default) | `openai` | `OPENAI_API_KEY` |
| Google Gemini | `google` | `GOOGLE_GENERATIVE_AI_API_KEY` |
| Anthropic Claude | `anthropic` | `ANTHROPIC_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |

---

## Good to know

- All scripts use AI SDK v7. Agent loops stop with `stopWhen: stepCountIs(N)`, which replaced the old `maxSteps`.
- `workspaceId` goes on the `MemoryClient`, not on `createConversation()`.
- Script 4 also saves each reasoning step, the same trace the Next.js demo shows in its side panel.
- `mcp.mjs` stops any database call after 30 seconds and cuts results over 50,000 characters. The model is told to write a smaller query instead of the script hanging.
