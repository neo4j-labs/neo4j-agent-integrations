# Neo4j AI Chat — Vercel AI SDK Demo

A full-stack chat application that combines **OpenAI gpt-5.4-mini**, **Neo4j Agent Memory Service (NAMS)** for persistent conversation memory, and an optional **MCP (Model Context Protocol)** connection to a Neo4j graph database for live Cypher query tools.

Built with [Next.js 14](https://nextjs.org/) and the [Vercel AI SDK](https://sdk.vercel.ai/).

---

## Features

- Multi-session chat with a collapsible sidebar and auto-generated titles
- Persistent memory across sessions via NAMS (semantic search, reflections, observations)
- Per-message `🧠 Agent Memory` badge showing what context was injected
- Optional live Neo4j graph querying via MCP tools (`read-cypher`, `get-schema`, etc.)
- Dark/light theme toggle, persisted in a browser cookie
- Streaming responses with tool-call display and thinking indicator
- Responsive layout (mobile, tablet, desktop)

---

## Architecture overview

```
Browser (React + NDL)
  │
  ├─ GET  /api/sessions   — load/create session store (cookie-backed)
  ├─ POST /api/sessions   — create a new chat session
  ├─ PATCH /api/sessions  — rename session / switch active session / toggle theme
  ├─ DELETE /api/sessions — delete a session
  │
  ├─ GET  /api/chat       — load conversation history from NAMS
  ├─ POST /api/chat       — send a message → stream a response
  └─ DELETE /api/chat     — delete a conversation from NAMS
```

### Request lifecycle (POST /api/chat)

```
① Parse body → { messages, sessionId, userId, conversationId, previousConversationIds }
② ensureConversation() — create or reuse a NAMS conversation
③ Retrieve memory context:
     a. getConversationContext()       — recent messages + reflections + observations
     b. searchMemoryContext()          — semantic search within current conversation
     c. searchPreviousConversations()  — semantic search across previous sessions (if provided)
     d. searchUserMemoryContext()      — user-level search across all their conversations (fallback)
     e. Inject stored recent messages not yet in the UI (e.g. after page refresh)
④ Persist user message to NAMS (fire-and-forget)
⑤ getNeo4jMcpTools() — lazily connect to MCP server (if MCP_URL is set)
   streamText() with:
     - model:    gpt-5.4-mini
     - system:   BASE_SYSTEM_PROMPT + injected memory context + memory instruction
     - messages: history-from-memory + system context + UI conversation history
     - tools:    Neo4j MCP tools (if available)
     - stopWhen: stepCountIs(5) — max 5 agentic loop iterations
⑥ onFinish: persist assistant reply to NAMS
   If first message: generateTitle() → emit data-session-title event
   Stream response back via createUIMessageStreamResponse
```

### Key source files

| File | Purpose |
|---|---|
| [Chat/chat.ts](Chat/chat.ts) | Memory client, MCP client, all NAMS operations |
| [Chat/chatComponent.tsx](Chat/chatComponent.tsx) | React chat UI — messages, memory badges, tool call display |
| [app/api/chat/route.ts](app/api/chat/route.ts) | Next.js route: GET/POST/DELETE for chat |
| [app/api/sessions/route.ts](app/api/sessions/route.ts) | Next.js route: GET/POST/PATCH/DELETE for sessions |
| [app/page.tsx](app/page.tsx) | Root page — sidebar, session management, theme |
| [lib/constants.ts](lib/constants.ts) | `BASE_SYSTEM_PROMPT` — graph schema and Cypher guidelines |
| [lib/title.ts](lib/title.ts) | Auto-title generation for new sessions |

---

## Prerequisites

- **Node.js 20+**
- **OpenAI API key** (`sk-…`)
- **NAMS API key** — Neo4j Agent Memory Service key (`nams_…`)
- **MEMORY_WORKSPACE_ID** — to scope memory to a specific workspace
- **MCP server URL** (optional) — to enable live Neo4j graph querying
- **MCP_NEO4J_USERNAME** (optional) — credentials
- **MCP_NEO4J_PASSWORD** (optional) — credentials

---

## Setup

**1. Install dependencies**

```bash
cd vercel-agent/vercel_agent_demo
npm install --legacy-peer-deps
```

**2. Configure environment variables**

```bash
cp .env.local.example .env.local
```

Edit `.env.local`:

```env
# Required
OPENAI_API_KEY=sk-...
MEMORY_API_KEY=nams_...
MEMORY_WORKSPACE_ID=your-workspace-id

# Optional — connect to a Neo4j MCP server for live graph queries
MCP_URL=https://your-neo4j-instance.com/mcp
MCP_NEO4J_USERNAME=neo4j
MCP_NEO4J_PASSWORD=your-password
```

> Next.js reads `.env.local` at startup. **Restart the dev server** after any change.

---

## Running the app

```bash
npm run dev       # development with hot reload
npm run build     # production build
npm run start     # serve production build
```

Open [http://localhost:3000](http://localhost:3000).

---

## Memory system

### How messages are stored and retrieved

Every user message and assistant response is persisted to NAMS immediately after each turn. On the next request the server runs a layered retrieval pipeline:

1. **`getConversationContext`** — fetches recent messages, reflections, and observations for the current conversation from NAMS.
2. **`searchMemoryContext`** — runs a semantic similarity search against messages stored in the current conversation (threshold `0.5`).
3. **`searchPreviousConversations`** — if no hits found and the client provided prior conversation IDs, searches those sessions.
4. **`searchUserMemoryContext`** — last-resort fallback: lists all conversations for the user via the NAMS SDK and runs semantic search on each.
5. **Recent-from-memory injection** — any stored messages not already present in the UI (e.g. after a page refresh) are injected directly into the LLM prompt as conversation history.

All retrieved context is deduplicated against the messages the UI already carries before being sent to the model.

### Memory badge

Each assistant response shows a `🧠 Agent Memory` badge when context was injected:

| Badge label | Source |
|---|---|
| **recent** | Messages from the current UI conversation + stored messages injected from NAMS |
| **semantic** | Past messages retrieved by similarity search (current conv, prev convs, or user-level) |
| **reflections** | Distilled summaries generated by NAMS over long conversations |
| **observations** | Entity-level facts extracted and stored by NAMS |

The badge only appears when at least one count is non-zero.

### Semantic search threshold

The similarity threshold is set to **`0.5`** (in `Chat/chat.ts` → `GOOD_MATCH_THRESHOLD`). Lowering this value increases recall (more matches, possibly less precise); raising it increases precision (fewer but more relevant matches). The NAMS SDK default is `0.7`.

### Model instruction

The system prompt always includes an explicit memory instruction:

- **Strong memory** (semantic hits ≥ 1): model is instructed to strongly prefer retrieved context and skip DB tool calls unless explicitly asked for live data.
- **No semantic hits, but `[UserContext]` present**: model is told to check context and conversation history before calling any tool.
- **No context at all**: model is told to check conversation history before calling any tool.

---

## Testing

### Basic memory recall

1. Send a message: `My name is Alice and I work in data engineering.`
2. Continue the conversation for a few more turns.
3. Click **New chat** in the sidebar to start a fresh session.
4. Ask: `What do you know about me?`
5. The assistant should recall details from the previous session via semantic search.

### Follow-up questions in the same session

1. Ask: `Tell me about Google in the graph.`
2. Then ask: `What subsidiaries of the company we discussed?`
3. The server logs will show that the second query finds a semantic hit for "Google" in the current conversation, and the model uses that context before deciding whether a DB call is needed.

### Conversation history on reload

Refresh the page or re-select a session. The conversation reloads from NAMS — not from the browser. This is confirmed in the server logs by the `recent-from-memory` count.

### Neo4j graph queries (requires MCP_URL)

With `MCP_URL` configured, try:

- `What organizations are in the graph?`
- `Find the top 5 most connected nodes`
- `Show me relationships between Person and Organization`

Each tool call (e.g. `read-cypher`) appears as a `🔧 tool-name · Xms` chip in the response. MCP tools also appear inside the memory badge under **🔧 MCP tools used**.

### Session management

| Action | How to test |
|---|---|
| Create a new session | Click **New chat** in the sidebar |
| Rename a session | Hover the session → click the pencil icon |
| Delete a session | Hover the session → click the trash icon |
| Switch sessions | Click any session in the sidebar |
| Persist theme | Toggle dark/light — refresh; theme is remembered in the cookie |

---

## Server-side console logs

With `npm run dev`, the terminal prints a numbered trace of the full memory flow for every request.

**GET (history load on page open):**
```
────────────────────────────────────────────────────────────
[chat/GET] ① Loading history | session: <id> | existingConv: none
[Memory:Conversation] Creating new conversation for user/session: <id>
[Memory:Conversation] Created → id: <conv-uuid> (42ms)
[Memory:Context] Fetching context for conversation: <conv-uuid>
[Memory:Context] Retrieved in 38ms → 2 recent message(s), 0 reflection(s), 0 observation(s)
[Memory:Context]   [1] user: "Tell me about Google in the graph"
[Memory:Context]   [2] assistant: "Here's the available information…"
[chat/GET] ② Returning 2 stored message(s) to UI
```

**POST (each chat turn):**
```
════════════════════════════════════════════════════════════
[chat/POST] ① Incoming query: "What subsidiaries of the company we discussed?"
[chat/POST]   session: <id> | existingConv: <conv-uuid> | prevConvs: 0
[Memory:Conversation] Reusing existing conversation: <conv-uuid>
[chat/POST] ② UI carries 3 message(s) in this request

[chat/POST] ③ Retrieving memory context…
[Memory:Context] Fetching context for conversation: <conv-uuid>
[Memory:Context] Retrieved in 31ms → 2 recent message(s), 0 reflection(s), 0 observation(s)
[Memory:Search] Searching current conversation … [threshold: 0.5, limit: 5]
[Memory:Search] Current conversation → 1 hit(s) (55ms)
[Memory:Search]   [1] "Tell me about Google in the graph"
[chat/POST] ③ Memory retrieval summary:
[chat/POST]   • recent-from-memory (not in UI): 0
[chat/POST]   • semantic hits (current conv):    1
[chat/POST]   • semantic hits (prev convs):      0
[chat/POST]   • semantic hits (user-level):      0
[chat/POST]   • reflections:                     0
[chat/POST]   • observations:                    0
[chat/POST]   → Total context msgs sent to LLM:  4

[chat/POST] ④ Storing user message to memory (async)…
[Memory:Store] Persisting user message to <conv-uuid>: "What subsidiaries…"
[Memory:Store] ✓ user message stored (28ms)

[chat/POST] ⑤ Tools loaded: get-schema, list-gds-procedures, read-cypher
[chat/POST] ⑤ Agent loop starting | model: gpt-5.4-mini | maxSteps: 5 | hasStrongMemory: true

[chat/POST] ⑥ Agent finished in 2 step(s)
[chat/POST] ⑥ Storing assistant response to memory…
[Memory:Store] Persisting assistant message to <conv-uuid>: "Here are the subsidiaries…"
[Memory:Store] ✓ assistant message stored (31ms)
[chat/POST] ⑥ ✓ Assistant response stored. Memory flow complete.
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `MEMORY_API_KEY is not configured` | Key missing from `.env.local` | Add `MEMORY_API_KEY=nams_…` and restart |
| `Memory service unavailable` (503) | NAMS unreachable or wrong key | Verify the key and `MEMORY_ENDPOINT` (defaults to `https://memory.neo4jlabs.com/v1`) |
| Memory badge never appears | No prior history for this user | Send a few messages; badges appear once NAMS has stored context |
| `0 conversation matches` in logs | Semantic similarity below threshold | Lower `GOOD_MATCH_THRESHOLD` in `Chat/chat.ts` (currently `0.5`); check that messages were stored in the previous turn |
| History does not reload after refresh | Wrong `conversationId` in the session cookie | Clear cookies for `localhost` and retry |
| `recent-from-memory` always 0 | UI already carries all messages | Expected — the injection only fires when the UI is missing stored messages (e.g. first load of an existing conversation) |
| MCP tools not available | `MCP_URL` not set or server unreachable | Check `MCP_URL`, `MCP_NEO4J_USERNAME`, `MCP_NEO4J_PASSWORD` |
| Tool call shown as `✗ error` in the UI | Cypher query failed or returned too many results | Refine the query with `LIMIT` and specific property selectors |
| Responses cut off for large results | 50 000-character truncation limit | Use a more specific Cypher query — the truncation notice appears inline |
