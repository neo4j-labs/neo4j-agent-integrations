# NAMS Chat — a chat app that remembers you

A small Next.js chat app built with the [Vercel AI SDK](https://ai-sdk.dev). It remembers what you tell it, even after you reload the page or restart the server. The memory lives in **NAMS** (Neo4j Agent Memory System), a hosted service that stores memory in a Neo4j graph.

All the memory code comes from one npm package, [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider). This app shows the four ways to use it.

---

## Quick start

```bash
cd vercel-agent/vercel_Nams_demo
npm install
cp .env.local.example .env.local   # add NAMS_API_KEY and OPENAI_API_KEY
npm run dev                        # pick a memory mode (or memory off), then open http://localhost:3000
```

- Get a free `NAMS_API_KEY` at [memory.neo4jlabs.com](https://memory.neo4jlabs.com).
- Needs Node 22.23.4 or newer, the minimum both NAMS packages declare. A plain `npm install` works, no extra flags.
- `npm install` takes `@neo4j-labs/nams-ai-provider` 0.5.0 and `@neo4j-labs/agent-memory` 0.6.0 from npm. Don't use an older `agent-memory`: 0.5.0 sends a `threshold` field that hosted NAMS rejects, so every message search comes back empty.

---

## The four memory modes, and memory off

When you run `npm run dev`, the terminal first asks `Memory on? [Y/n]`. Enter or `y` keeps memory on and shows the mode menu. Press Enter there for `provider`, or type a number or name. Type `n` to turn memory off instead. That skips the menu: each message is answered on its own, nothing is loaded or saved, and earlier messages in the chat aren't sent. The choice applies to that run only and isn't saved to a file. `NAMS_MODE` is not read from `.env.local` or the shell. Non-interactive shells skip the prompts and use `provider`. All four memory modes save to the same place, so you can switch between them without losing anything. The header shows the active mode, such as `Memory: provider` or `Memory off`.

| Mode | Who takes care of memory | Memory calls shown in the chat? |
|---|---|---|
| `provider` (default) | A wrapper around the AI model. It adds memories before each answer and saves the turn after. | No |
| `middleware` | The same wrapper, placed on a model you already have. | No |
| `tools` | The AI model itself, by calling two tools: `query_memory` and `store_memory`. | Yes |
| `hooks` | This app's own code. It loads the saved chat before each answer and saves every turn after. | No |
| `off` (answer `n` to `Memory on?`) | No memory. Each message is answered on its own, and nothing is loaded or saved. | No |

**Which one should I pick?**

- Just want memory to work? Use **provider**.
- Already have a model object? Use **middleware**.
- Want to *see* the memory reads and writes? Use **tools**.
- Want every turn saved, whatever the model decides? Use **hooks**.
- Don't want memory at all? Answer `n` to `Memory on?`.

Any other value makes the chat return an error, so a typo can't quietly turn memory off.

### What each mode looks like in code

```ts
import { createNams, createNamsProvider } from '@neo4j-labs/nams-ai-provider';
import { openai } from '@ai-sdk/openai';

// provider: build the model through NAMS
const model = createNamsProvider({ apiKey, baseProvider: openai, scope: { userId } })
  .languageModel('gpt-5.6-luna');

// middleware: wrap a model you already have
const wrapped = createNams({ apiKey }).wrap(openai('gpt-5.6-luna'), { userId });

// tools: give the model memory tools (plus any database tools)
const { tools, close } = await createNams({ apiKey }).toolsWithMcp({ userId });

// hooks: load the chat yourself, then save the turn yourself
const session  = createNams({ apiKey }).hooks({ userId });
const messages = [...(await session.loadSession()), { role: 'user', content: userText }];
// ...run the model with `messages`, then in onEnd:
await session.onFinish({ prompt: userText })(event);
```

The real version is in [`app/api/chat/route.ts`](app/api/chat/route.ts).

A few details:

- **Every mode:** the browser sends only its newest message. The route loads the earlier turns from NAMS with `session.loadSession()`.
- **tools mode:** small models sometimes skip memory. `enforceQueryMemory()` makes the model read memory first. The route saves each turn's text itself, so the chat doesn't depend on the model calling `store_memory`.
- **hooks mode:** saves the conversation only, not separate long-term facts. It also saves each tool call and result as a `[tool-call] …` / `[tool-result] …` message tagged `namsKind`, and `loadSession()` leaves those out of the history it returns.
- Each mode has its own system prompt in [`lib/constants.ts`](lib/constants.ts), so the model is never told about tools it doesn't have.
- **Reasoning panel:** after each answer the route saves one reasoning step per agent step, in order, before the reply finishes. The panel reads them right after.

---

## Optional: let the agent query your Neo4j database

Point the app at a Neo4j MCP server and the agent can look things up in your graph, in any mode:

```env
MCP_URL=https://your-server/mcp
MCP_BEARER_TOKEN=...                           # or:
MCP_NEO4J_USERNAME=neo4j
MCP_NEO4J_PASSWORD=...
```

Each database call is stopped after 30 seconds, and results over 50,000 characters are cut short. The model gets a note telling it to write a smaller query. Without this, one heavy query could hang the reply for minutes.

Not sure which login your server wants? Run `curl -i -X POST $MCP_URL`. A `WWW-Authenticate: Bearer` reply means a token; `Basic` means username and password.

---

## Settings (`.env.local`)

| Variable | Needed? | What it does |
|---|---|---|
| `NAMS_API_KEY` | Yes | Your NAMS key. Without it, every chat request fails. |
| `OPENAI_API_KEY` | Yes | Your OpenAI key. |
| `MEMORY_WORKSPACE_ID` | No | Use a specific NAMS workspace. |
| `OPENAI_MODEL` | No | Model to use. Default `gpt-5.6-luna`. |
| `NAMS_EXTRACTION_MODEL` | No | Tools mode only: also turns each saved fact into graph entities. Costs one extra model call. |
| `MCP_URL` / `MCP_PORT` | No | Neo4j MCP server (see above). |
| `MCP_BEARER_TOKEN` or `MCP_NEO4J_USERNAME` + `MCP_NEO4J_PASSWORD` | No | Login for the MCP server. |
| `NEXT_ALLOWED_DEV_ORIGINS` | No | Extra hostnames allowed to open the dev server, e.g. a LAN IP. |

---

## Try it

For each mode, run `npm run dev` and pick it from the menu, then:

1. Send: *"My favourite colour is blue."*
2. Reload the page (the chat window empties).
3. Send: *"What's my favourite colour?"* The answer should be **blue**.

What you'll see in the terminal:

| Mode | Log line to look for |
|---|---|
| any | `[chat]   restored N earlier turns from NAMS` |
| `provider` / `middleware` | `[chat] Done \| steps=1 queries=0 stores=0` |
| `tools` | `queries=1 stores=1`, and the steps show up in the Reasoning panel |

To see the saved reasoning steps: `curl "http://localhost:3000/api/reasoning?userId=<id>"`. The id is in your browser's `localStorage` under `nams-session-id`.

### Automated tests

```bash
npm test     # 33 tests, no real keys needed
```

They check each mode's wiring against a fake version of the package.

---

## Project layout

```
app/api/chat/route.ts        the chat endpoint: picks the mode and runs the agent
app/api/reasoning/route.ts   returns saved reasoning steps for the side panel
components/chat/             the chat UI, memory panel and reasoning panel
lib/constants.ts             system prompts, one per mode
lib/neo4j-mcp.ts             connects to the Neo4j MCP server
test/                        route tests (vitest)
```

---

## Troubleshooting

**It doesn't remember me.**
- Did you restart the server after editing `.env.local`?
- Clearing your browser's site data makes you a new user.
- In tools mode, check that the Reasoning panel shows a `store_memory` step.

**The model never uses memory tools (tools mode).** Check the log says `tools=2` or more. If it does, try a bigger model: `OPENAI_MODEL=gpt-5.6-terra`.

**The MCP connection fails.** An `HTTP 401` usually means the wrong *kind* of login (token vs. username/password). The log names the kind the server wants.

**"I ran out of steps…"** The agent used all 10 steps without answering. Try a clearer question or a bigger model.

**"read-cypher took longer than 30s".** The model wrote a query that was too heavy for the server. It usually retries with a smaller one. If it keeps happening, ask a narrower question.

**`NAMS_API_KEY is not set`.** Add the key to `.env.local` and restart.

---

## Known limits of hosted NAMS

These come from the NAMS service and the package, not from this app:

- **Long-term facts saved before the per-user change are not recalled.** Each fact is now stored under the user who said it, and only that user gets it back. Older facts have no user, so the app skips them. Set `workspaceGraph: true` in the NAMS config to also recall those shared facts. Another user's facts are never recalled.

Please report problems at [neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory).

---

## Links

- [NAMS](https://memory.neo4jlabs.com)
- [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider) ([source](https://github.com/neo4j-labs/agent-memory/tree/main/typescript/packages/vercel-ai-provider))
- [Vercel AI SDK docs](https://ai-sdk.dev/docs)
