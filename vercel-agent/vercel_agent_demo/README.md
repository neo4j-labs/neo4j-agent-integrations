# Neo4j AI Chat — Vercel AI SDK Demo

A full-stack chat application that combines **OpenAI GPT-4o-mini**, **Neo4j Agent Memory Service (NAMS)** for persistent conversation memory, and an optional **MCP (Model Context Protocol)** connection to a Neo4j graph database for live Cypher query tools.

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
1. Parse body  →  { messages, sessionId, userId, conversationId, previousConversationIds }
2. ensureConversation()   — create or reuse a NAMS conversation
3. Retrieve memory context (in parallel via runWithMcpTracker):
     a. searchMemoryContext()        — semantic search within current conversation
     b. searchPreviousConversations() — semantic search across previous sessions
     c. searchUserMemoryContext()    — user-level cross-session search (fallback)
     d. getConversationContext()     — reflections + observations from NAMS
4. Inject retrieved context as system messages into the prompt
5. getNeo4jMcpTools()    — lazily connect to MCP server (if MCP_URL is set)
6. streamText() with:
     - model:   gpt-4o-mini
     - system:  BASE_SYSTEM_PROMPT + injected memory context
     - messages: system context + UI conversation history
     - tools:   Neo4j MCP tools (if available)
     - stopWhen: stepCountIs(5)  — max 5 agentic loop iterations
7. Stream response back via createUIMessageStreamResponse
8. onFinish: persist assistant reply to NAMS
9. If first message: generateTitle() → emit data-session-title event
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

## Testing

### Basic memory recall

1. Send a message: `My name is Alice and I work in data engineering.`
2. Continue the conversation for a few more turns.
3. Click **New chat** in the sidebar to start a fresh session.
4. Ask: `What do you know about me?`
5. The assistant should recall details from the previous session via semantic search.

### Memory badge verification

Each assistant response shows a `🧠 Agent Memory` badge when context was injected. The badge shows counts for:

| Badge | Source |
|---|---|
| **recent** | Messages from the current conversation window |
| **semantic** | Past messages retrieved by similarity search |
| **reflections** | Distilled summaries generated by NAMS |
| **observations** | Entity-level facts stored in long-term memory |

The badge only appears when at least one of these counts is non-zero. On the very first message of a brand-new user it will be absent — send a few messages first.

### Conversation history on reload

Refresh the page or re-select a session. The conversation should reload from NAMS (not from the browser).

### Neo4j graph queries (requires MCP_URL)

With `MCP_URL` configured, try:

- `What organizations are in the graph?`
- `Find the top 5 most connected nodes`
- `Show me relationships between Person and Organization`

Each tool call (e.g. `read-cypher`) appears as a `🔧 tool-name · Xms` chip in the response. The MCP tools also appear inside the memory badge under **🔧 MCP tools used**.

### Session management

| Action | How to test |
|---|---|
| Create a new session | Click **New chat** in the sidebar |
| Rename a session | Hover the session → click the pencil icon |
| Delete a session | Hover the session → click the trash icon |
| Switch sessions | Click any session in the sidebar |
| Persist theme | Toggle dark/light — refresh; theme is remembered in the cookie |

### Verify server-side behaviour

With `npm run dev`, the terminal logs key events:

```
[chat/route] User query: "…"
[Memory Retrieved] 2 conversation matches, 0 previous-conversation matches, …
[Tools Loaded] Available: read-cypher, get-schema, …
[Executing Agent Loop] Model: gpt-4o-mini | Max steps: 5
[Agent Complete] Generated response in 1 step(s). Message persisted to Agent Memory.
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `MEMORY_API_KEY is not configured` | Key missing from `.env.local` | Add `MEMORY_API_KEY=nams_…` and restart |
| `Memory service unavailable` (503) | NAMS unreachable or wrong key | Verify the key and `MEMORY_ENDPOINT` (defaults to `https://memory.neo4jlabs.com/v1`) |
| Memory badge never appears | No prior history for this user | Send a few messages; badges appear once NAMS has stored context |
| History does not reload after refresh | Wrong `conversationId` in the session cookie | Clear cookies for `localhost` and retry |
| MCP tools not available | `MCP_URL` not set or server unreachable | Check `MCP_URL`, `MCP_NEO4J_USERNAME`, `MCP_NEO4J_PASSWORD` |
| Tool call shown as `✗ error` in the UI | Cypher query failed or returned too many results | Refine the query with `LIMIT` and specific property selectors |
| Responses cut off for large results | 50 000-character truncation limit | Use a more specific Cypher query — the truncation notice appears inline |
