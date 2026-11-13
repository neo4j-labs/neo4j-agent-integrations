# NAMS Chat — a chat app that remembers you

A small Next.js chat app built with the [Vercel AI SDK](https://ai-sdk.dev). It remembers what you tell it, even after you reload the page or restart the server. The memory lives in **NAMS** (Neo4j Agent Memory System), a hosted service that stores memory in a Neo4j graph.

All the memory code comes from one npm package, [`@neo4j-labs/nams-ai-provider`](https://www.npmjs.com/package/@neo4j-labs/nams-ai-provider). This app shows the four ways to use it.

---

## Quick start

```bash
cd vercel-agent/vercel_Nams_demo
npm install
cp .env.local.example .env.local   # add NAMS_API_KEY and OPENAI_API_KEY
npm run dev                        # memory on? which mode? then open http://localhost:3000
```

- Get a free `NAMS_API_KEY` at [memory.neo4jlabs.com](https://memory.neo4jlabs.com).
- Needs Node 22.23.4 or newer, the minimum both NAMS packages declare. A plain `npm install` works, no extra flags.
- `npm install` takes `@neo4j-labs/nams-ai-provider` 0.5.0 and `@neo4j-labs/agent-memory` 0.6.0 from npm. Don't use an older `agent-memory`: 0.5.0 sends a `threshold` field that hosted NAMS rejects, so every message search comes back empty.

---

## The four memory modes, and memory off

When you run `npm run dev`, the terminal first asks `Memory on?`. Answer `n` to turn memory off. Otherwise it lists the four modes and marks the current one with `← current`. Type a number or a name, or press Enter to keep the current one.

The current mode is `NAMS_MODE` from your shell, then `.env.local`, then `.env`, and `provider` if none sets it. So with `NAMS_MODE=tools` in `.env.local`, pressing Enter twice runs `tools`. Your pick applies to that run only; no file is changed. Shells without a terminal (CI, piped input) skip the questions and use the current mode as it is.

All four memory modes save to the same place, so you can switch between them without losing anything. The header shows the active mode as a chip, such as `memory: provider` or `memory: off`. Hover it to see which API that mode uses.

| Mode | Who takes care of memory | Memory calls shown in the chat? |
|---|---|---|
| `provider` (default) | A wrapper around the AI model. It adds memories before each answer and saves the turn after. | No |
| `middleware` | The same wrapper, placed on a model you already have. | No |
| `tools` | The AI model itself, by calling two tools: `query_memory` and `store_memory`. | Yes |
| `hooks` | This app's own code. It loads the saved chat before each answer and saves every turn after. | No |
| `off` (answer `n` to `Memory on?`) | No memory. The model sees only the messages in this chat, and nothing is loaded or saved. | No |

**Which one should I pick?**

- Just want memory to work? Use **provider**.
- Already have a model object? Use **middleware**.
- Want to *see* the memory reads and writes? Use **tools**.
- Want every turn saved, whatever the model decides? Use **hooks**.
- Want to see what it's like without memory? Answer `n` to `Memory on?`.

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

- **Every memory mode:** the browser sends only its newest message. The route loads the earlier turns from NAMS with `session.loadSession()`.
- **off:** there is no NAMS to load from, so the browser also sends this chat's transcript. Chat history is not memory: click **New chat** or reload and it's gone.
- **tools mode:** small models sometimes skip memory. `enforceQueryMemory()` makes the model read memory first. The route saves each turn's text itself, so the chat doesn't depend on the model calling `store_memory`.
- **hooks mode:** saves the conversation only, not separate long-term facts. It also saves each tool call and result as a `[tool-call] …` / `[tool-result] …` message tagged `namsKind`, and `loadSession()` leaves those out of the history it returns.
- Each mode has its own system prompt in [`lib/constants.ts`](lib/constants.ts), so the model is never told about tools it doesn't have.
- **hooks mode also writes the reasoning trail:** after each answer the route saves one NAMS reasoning step per agent step, with the model's reasoning, the tools it called and each call's result. No other mode writes one, so the `reasoning` tab in the memory panel fills only in hooks mode.
- The route asks OpenAI for reasoning summaries (`reasoningSummary: 'auto'`), so the Reasoning Trace panel can show the model's thinking. The model decides when to reason; a short greeting often has none.

---

## The chat UI

Two panels sit above every answer.

**Agent Memory** shows what NAMS holds for you, in five tabs: `recent`, `observations`, `insights`, `entities` and `reasoning`. After each answer the app reads them through [`app/api/memory/route.ts`](app/api/memory/route.ts) instead of watching for tool calls, so the panel works in every mode. In `provider`, `middleware` and `hooks` the model never calls a memory tool, so there would otherwise be nothing to show. `entities` is searched with your question and shows only your own entities, the same ones `query_memory` can return. Other users in the workspace have their own.

Its header also carries a badge naming what drove memory on this turn. That is how you tell the modes apart at a glance:

| Mode | Badge |
|---|---|
| `provider` | `wrapped provider · never a tool call` |
| `middleware` | `wrapped model · never a tool call` |
| `tools` | `model called 2 memory tools`, or `model called no memory tool` on the turns it skips them |
| `hooks` | `app hooks · 2 reasoning steps saved` |

Expand the panel to see a sentence on how that mode worked, and in `tools` mode a chip for each memory call.

**Reasoning Trace** shows the agent's own steps for this answer, live as they stream: its thinking, and every tool call with its input, status and result. In `tools` mode `query_memory` and `store_memory` show up here in full. In `provider`, `middleware` and `hooks` memory never appears here, because it happens around the model rather than as a tool. Only database tools do.

On an empty chat, the greeting tells you how many memories NAMS already holds from earlier chats. The **+** button in the header starts a new chat for the same user.

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
| `NAMS_MODE` | No | The mode `npm run dev` offers first: `provider` (default), `middleware`, `tools`, `hooks` or `off`. |
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
2. Click **New chat** (or reload the page). The chat window empties.
3. Send: *"What's my favourite colour?"* The answer should be **blue**.

What you'll see in the terminal:

| Mode | Log line to look for |
|---|---|
| any memory mode | `[chat]   restored N earlier turns from NAMS` |
| `off` | `[chat]   N earlier turns from this chat (memory off)`, and the answer to step 3 is that it doesn't know |
| `provider` / `middleware` | `[chat] Done \| steps=1 queries=0 stores=0` |
| `tools` | `queries=1 stores=1`, and both calls show up in the Reasoning Trace |

To see what the memory panel reads: `curl "http://localhost:3000/api/memory?userId=<id>&q=colour"`. The id is in your browser's `localStorage` under `nams-session-id`.

### Automated tests

```bash
npm test     # 43 tests, no real keys needed
```

They check each mode's wiring and the memory snapshot against a fake version of the package.

---

## Project layout

```
app/page.tsx                 reads NAMS_MODE and renders the chat
app/api/chat/route.ts        the chat endpoint: picks the mode and runs the agent
app/api/memory/route.ts      what NAMS holds for a user, for the Agent Memory panel
components/AppHeader.tsx     mode chip, New chat, dark mode
components/chat/             the chat, the Agent Memory panel and the Reasoning Trace
lib/mode.ts                  NAMS_MODE parsing and NAMS settings
lib/constants.ts             system prompts, one per mode
scripts/dev.mjs              the `npm run dev` mode picker
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
