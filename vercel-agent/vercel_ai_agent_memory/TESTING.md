# Testing Guide — Neo4j Agent Memory with Vercel AI

This guide explains how to run and test the chat application using either of the two supported memory transports:

| Transport | Auth mechanism | When to use |
|---|---|---|
| **SDK** (Option A) | `MEMORY_API_KEY` | Default. Uses `@neo4j-labs/agent-memory` client directly over REST. |
| **MCP** (Option B) | `NEO4J_USERNAME` + `NEO4J_PASSWORD` | Connects via Model Context Protocol (StreamableHTTP + Basic auth). |

Both transports talk to the same hosted Neo4j Agent Memory Service (NAMS) at `memory.neo4jlabs.com`. The transport choice only affects how the app authenticates and communicates — the memory behaviour (short-term context, semantic search, reflections, observations) is identical.

---

## Prerequisites

- Node.js 20+
- An OpenAI API key
- One of:
  - A NAMS API key (`nams_…`) — for SDK transport
  - A Neo4j username + password — for MCP transport

Install dependencies once:

```bash
cd vercel-agent/vercel_ai_agent_memory
npm install
```

---

## Project structure (relevant files)

```
vercel_ai_agent_memory/
├── Chat/
│   ├── chat.ts            # Memory transport layer — SDK and MCP backends with if/else routing
│   └── chatComponent.tsx  # React chat UI, shows 🧠 Agent Memory badges per message
├── app/
│   └── api/
│       └── chat/
│           └── route.ts   # Next.js API route — GET (load history), POST (stream), DELETE (clear)
├── .env.local.example     # Template — copy to .env.local and fill in credentials
└── .env.local             # Your local credentials (git-ignored)
```

---

## Option A — SDK transport (MEMORY_API_KEY)

### 1. Configure credentials

Copy the example env file:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` and set:

```env
OPENAI_API_KEY=sk-...

# SDK transport — uncomment and fill in
MEMORY_API_KEY=nams_...
```

Leave `NEO4J_USERNAME` and `NEO4J_PASSWORD` absent (or commented out). As long as those two are not set, the app uses the SDK path.

### 2. Start the dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 3. What to test

#### Basic memory recall
1. Send a message: `My name is Alice and I work in data engineering.`
2. Continue the conversation normally for a few more turns.
3. Start a **new session** (use the session switcher in the sidebar).
4. Ask: `What do you know about me?`
5. The assistant should recall details from the previous session via semantic search.

#### Memory badge (per-message context indicator)
Each assistant response shows a `🧠 Agent Memory` badge when memory context was injected. Hover to see:
- **recent** — messages from the current conversation window
- **semantic** — past messages retrieved by similarity search
- **reflections** — distilled summaries the service generated
- **observations** — entity-level facts stored in long-term memory

#### Conversation history on reload
Refresh the page or re-select a session. The conversation history should reload from NAMS (not the browser).

#### Verify the transport in logs
With `npm run dev`, the terminal will show `[chat]` log lines. For SDK transport you will NOT see any `MCP` references in the logs.

---

## Option B — MCP transport (NEO4J_USERNAME + NEO4J_PASSWORD)

### 1. Configure credentials

Edit `.env.local`:

```env
OPENAI_API_KEY=sk-...

# MCP transport — set both to activate
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-password

# Optional overrides (defaults shown)
# MCP_URL=https://memory.neo4jlabs.com/mcp
# MEMORY_REST_URL=https://memory.neo4jlabs.com/v1
```

Remove or comment out `MEMORY_API_KEY`. When both `NEO4J_USERNAME` and `NEO4J_PASSWORD` are present, the app switches to MCP transport automatically — no code change needed.

> **How the credentials are used:** `NEO4J_USERNAME:NEO4J_PASSWORD` is base64-encoded and sent as an `Authorization: Basic <encoded>` header on every request to the MCP endpoint (`MCP_URL`). This matches the `StreamableHTTPConnectionParams` pattern used by the Python MCP SDK.

### 2. Start the dev server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 3. What to test

Run the same test cases from Option A — the user-facing behaviour is identical. To confirm MCP transport is active:

#### Confirm transport selection at startup
The transport is selected on the first memory operation. Check the terminal for:
- No `MEMORY_API_KEY` error → SDK path is not taken
- A successful first response with the memory badge → MCP handshake succeeded

#### Force an error to confirm MCP is being used
Temporarily set a wrong password:

```env
NEO4J_PASSWORD=wrong
```

Restart the server and send a message. The app should respond with `Memory service unavailable` (503) — confirming it is hitting the MCP endpoint, not the SDK path.

Restore the correct password and restart.

#### Conversation delete (MCP path)
MCP does not expose a delete tool. The app falls back to a direct REST `DELETE` call using Basic auth against `MEMORY_REST_URL`. To test:
1. Open a conversation and send a few messages.
2. Delete the session from the sidebar.
3. Reopen the same session — history should be empty.

---

## Switching between transports

No code changes are needed. Transport is selected at runtime based on which env vars are present:

| `.env.local` state | Transport used |
|---|---|
| `MEMORY_API_KEY` set, `NEO4J_USERNAME`/`NEO4J_PASSWORD` absent | SDK |
| `NEO4J_USERNAME` + `NEO4J_PASSWORD` both set | MCP |
| All three set | MCP (takes precedence) |
| None set | Error on first memory call |

After editing `.env.local`, **restart the dev server** — Next.js does not hot-reload env files.

```bash
# Ctrl+C to stop, then:
npm run dev
```

---

## How the transport routing works (code reference)

`useMcpTransport()` in [Chat/chat.ts](Chat/chat.ts) is the single decision point:

```ts
function useMcpTransport(): boolean {
  const username = process.env.NEO4J_USERNAME?.trim();
  const password = process.env.NEO4J_PASSWORD?.trim();
  return Boolean(username && password);
}
```

Every memory operation (`ensureConversation`, `getConversationContext`, `addMessage`, `searchMemoryContext`, `deleteConversation`) checks this function and branches:

```ts
if (useMcpTransport()) {
  // MCP path — calls memory_* tools via StreamableHTTP JSON-RPC
} else {
  // SDK path — calls getSdkClient().shortTerm.*
}
```

The MCP client is created lazily with:

```ts
createMCPClient({
  transport: {
    type: 'http',
    url: process.env.MCP_URL || 'https://memory.neo4jlabs.com/mcp',
    headers: {
      Authorization: `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`,
    },
  },
})
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `MEMORY_API_KEY is not configured` error | SDK transport selected but no key set | Add `MEMORY_API_KEY` to `.env.local` or switch to MCP |
| `NEO4J_USERNAME and NEO4J_PASSWORD are required` error | MCP transport attempted but credentials missing | Set both vars in `.env.local` |
| `Memory service unavailable` (503 on first message) | MCP handshake failed — wrong URL or credentials | Check `MCP_URL`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` |
| Memory badge never appears | Memory context is empty (new user / no history) | Send a few messages first; badges appear from the second session onward |
| History does not reload after page refresh | Wrong `conversationId` stored in session cookie | Clear browser cookies for `localhost` and retry |
| Conversation delete fails in MCP mode | `MEMORY_REST_URL` unreachable or wrong Basic auth | Verify `NEO4J_USERNAME`/`NEO4J_PASSWORD` work against the REST endpoint |
| `MCP tool 'memory_*' error` in logs | Tool call rejected by NAMS MCP server | Check credentials; confirm the MCP server is reachable |
