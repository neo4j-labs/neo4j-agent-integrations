# NAMS Chat — Vercel AI SDK + Neo4j Agent Memory System

A production-ready Next.js chat application demonstrating **NAMS (Neo4j Agent Memory System)** integrated with the **Vercel AI SDK**. This repository serves as both a working example and a reusable template for building stateful AI agents that remember conversation context across sessions.

**Key features:**
- **Two integration modes**: Use NAMS as a custom provider (automatic memory) or custom tools (model-driven memory)
- **Persistent memory**: Long-term facts, user preferences, and interaction history stored in Neo4j
- **Cross-session retrieval**: Agents recall information from previous conversations
- **Production patterns**: Session management, error handling, streaming responses, reasoning traces
- **Extensible**: Easily customize memory schemas, retrieval strategies, and storage logic

---

## Quick Start (5 minutes)

Choose your integration mode and get up and running:

### Option A: Provider Mode (Recommended for beginners)
Automatic memory handling — NAMS is transparent to your model.

```bash
# 1. Clone and install
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/vercel-agent/vercel_Nams
npm install

# 2. Set environment
cp .env.local.example .env.local
# Edit .env.local: set MEMORY_API_KEY, OPENAI_API_KEY, NAMS_MODE=provider

# 3. Run
npm run dev
# Open http://localhost:3000
```

**In your code:**
```typescript
import { createNams } from '@/lib/nams';
import { streamText } from 'ai';
import { openai } from '@ai-sdk/openai';

const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const model = nams.wrap(openai('gpt-4o-mini'), { userId: 'user-123' });

const result = streamText({ model, messages });
```

### Option B: Tools Mode (For fine-grained control)
Model-driven memory — LLM decides when to query and store.

```bash
# Same setup, but set: NAMS_MODE=tools
export NAMS_MODE=tools
npm run dev
```

**In your code:**
```typescript
import { createNams } from '@/lib/nams';
import { streamText, stepCountIs } from 'ai';
import { openai } from '@ai-sdk/openai';

const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
const tools = nams.tools({ userId: 'user-123' });

const result = streamText({
  model: openai('gpt-4o-mini'),
  messages,
  tools,
  system: SYSTEM_PROMPT,  // Must instruct: query → answer → store
  stopWhen: stepCountIs(10),
});
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser (Next.js)                              │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  components/chat/ChatComponent.tsx  (useChat + DefaultChatTransport)│   │
│  │                                                                     │   │
│  │  • Generates a stable sessionId (localStorage key: nams-session-id) │   │
│  │  • Sends messages → POST /api/chat  {sessionId, conversationId}     │   │
│  │  • Receives streaming UIMessage parts + data-conversation-id event  │   │
│  │  • Fetches GET /api/reasoning?userId=&conversationId= after reply   │   │
│  │                                                                     │   │
│  │  ┌──────────────────────┐  ┌────────────────────────────────────┐  │   │
│  │  │   Agent Memory panel │  │        Reasoning Trace panel       │  │   │
│  │  │  recent │ observations│  │  step 1 → step 2 → step N         │  │   │
│  │  │         │ reasoning   │  │  reasoning / action / result      │  │   │
│  │  └──────────────────────┘  └────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │  HTTP (streaming NDJSON)
                                                                ▼
                                                                ┌─────────────────────────────────────────────────────────────────────────────┐
                                                                │                         Next.js API Routes (Node.js)                        │
                                                                │                                                                             │
                                                                │  POST /api/chat                          GET /api/reasoning                 │
                                                                │  ─────────────────────────────────────   ─────────────────────────────      │
                                                                │  1. Parse UIMessages + session IDs       1. Look up userId → convId         │
                                                                │  2. getOrCreateConversation (NAMS)       2. client.reasoning.listSteps()    │
                                                                │  3. addMessage (user turn)               3. Return step array as JSON       │
                                                                │  4. createNamsMemoryTools()                                                  │
                                                                │  5. streamText (OpenAI model)                                                │
                                                                │     ├─ system prompt: mandatory          ┌──────────────────────────────┐   │
                                                                │     │  query → answer → store cycle      │  NAMS Memory Tools (Vercel)  │   │
                                                                │     └─ tools ──────────────────────────▶│  query_memory / store_memory │   │
                                                                │  6. onFinish:                            └──────────────┬───────────────┘   │
                                                                │     ├─ addMessage (assistant turn)                      │                   │
                                                                │     └─ recordStep (reasoning trace)                     │                   │
                                                                └─────────────────────────────────────────────────────────┼───────────────────┘
                                                                                                                          │  HTTPS REST
                                                                                                                                                                                    ▼
                                                                                                                                                                                    ┌─────────────────────────────────────────────────────────────────────────────┐
                                                                                                                                                                                    │                    NAMS  —  https://memory.neo4jlabs.com/v1                 │
                                                                                                                                                                                    │                    (@neo4j-labs/agent-memory SDK)                           │
                                                                                                                                                                                    │                                                                             │
                                                                                                                                                                                    │  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
                                                                                                                                                                                    │  │   Short-Term Memory  │  │   Long-Term Memory   │  │  Reasoning Trace │  │
                                                                                                                                                                                    │  │  (conversation msgs) │  │  (graph entities)    │  │  (step records)  │  │
                                                                                                                                                                                    │  │                      │  │                      │  │                  │  │
                                                                                                                                                                                    │  │ • scoped per convId  │  │ • facts              │  │ • reasoning text │  │
                                                                                                                                                                                    │  │ • vector search      │  │ • user_preferences   │  │ • actionTaken    │  │
                                                                                                                                                                                    │  │ • cross-session scan │  │ • patterns           │  │ • result summary │  │
                                                                                                                                                                                    │  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
                                                                                                                                                                                    │                                                                             │
                                                                                                                                                                                    │                    Backed by a Neo4j AuraDB graph                           │
                                                                                                                                                                                    └─────────────────────────────────────────────────────────────────────────────┘
                                                                                                                                                                                    ```

                                                                                                                                                                                    ### Memory flow per turn

                                                                                                                                                                                    ```
                                                                                                                                                                                    User sends message
                                                                                                                                                                                           │
                                                                                                                                                                                                  ▼
                                                                                                                                                                                                   [tool] query_memory ──────────────────────────────────────────┐
                                                                                                                                                                                                          │  searches:                                             │
                                                                                                                                                                                                                 │  • current conversation (short-term, vector)          │
                                                                                                                                                                                                                        │  • past conversations for this userId (cross-session) │
                                                                                                                                                                                                                               │  • long-term graph entities                           │
                                                                                                                                                                                                                                      │  • prior reasoning steps                              │
                                                                                                                                                                                                                                             │◀──────────── returns ranked MemoryHit[] ──────────────┘
                                                                                                                                                                                                                                                    │
                                                                                                                                                                                                                                                           ▼
                                                                                                                                                                                                                                                            LLM composes answer  (personalised with retrieved context)
                                                                                                                                                                                                                                                                   │
                                                                                                                                                                                                                                                                          ▼
                                                                                                                                                                                                                                                                           [tool] store_memory
                                                                                                                                                                                                                                                                                  │  persists:
                                                                                                                                                                                                                                                                                         │  • interaction  → short-term conversation thread
                                                                                                                                                                                                                                                                                                │  • fact         → long-term graph entity
                                                                                                                                                                                                                                                                                                       │  • user_preference → long-term graph entity
                                                                                                                                                                                                                                                                                                              │  • pattern      → long-term graph entity
                                                                                                                                                                                                                                                                                                                     │
                                                                                                                                                                                                                                                                                                                            ▼
                                                                                                                                                                                                                                                                                                                             onFinish callback
                                                                                                                                                                                                                                                                                                                                    │  • addMessage (assistant turn) → short-term
                                                                                                                                                                                                                                                                                                                                           │  • recordStep (reasoning)      → reasoning trace
                                                                                                                                                                                                                                                                                                                                                  ▼
                                                                                                                                                                                                                                                                                                                                                   Response streams to browser
                                                                                                                                                                                                                                                                                                                                                   ```

                                                                                                                                                                                                                                                                                                                                                   ---

## Integration Modes — Choose One

NAMS provides **two independent integration modes** with the Vercel AI SDK. Both use the same Neo4j backend and memory architecture, but differ in control flow:

| Mode | Style | When to use | Pattern |
|------|-------|------------|---------|
| **Provider** | Automatic, model-agnostic | Fastest integration, memory always active | Mem0 / Letta |
| **Custom Tools** | Model-driven, explicit | Fine-grained control, visible tool traces | Supermemory / OpenAI Assistants |

### Environment configuration

```env
# .env.local
NAMS_MODE=provider        # (default) Automatic memory via model wrapping
# NAMS_MODE=tools         # Custom tools — model calls query_memory / store_memory
```

**Key difference**: 
- **Provider**: Memory retrieval/storage happens automatically on every request. Simple, deterministic.
- **Custom Tools**: Model decides when to call `query_memory` and `store_memory`. Visible in reasoning traces, more flexible.

                                                                                                                                                                                                                                                                                                                                                   ---

### Mode 1 — Provider (Automatic Memory)

Use `createNams().wrap()` to wrap your LLM. Memory is retrieved and stored transparently before and after each call.

**Setup:**

```typescript
// Once at module level (e.g., lib/nams-singleton.ts)
import { createNams } from '@/lib/nams';

export const nams = createNams({
  apiKey: process.env.MEMORY_API_KEY!,
  workspaceId: process.env.MEMORY_WORKSPACE_ID, // optional
});
```

**Per-request usage:**

```typescript
// In app/api/chat/route.ts (or anywhere you call streamText)
import { nams } from '@/lib/nams-singleton';
import { streamText } from 'ai';
import { openai } from '@ai-sdk/openai';

export async function POST(req: Request) {
  const { messages, userId, conversationId } = await req.json();
  
  // Wrap the model — memory is handled automatically
  const model = nams.wrap(openai('gpt-4o-mini'), {
    userId,
    conversationId, // optional: pin to specific conversation
  });
  
  // No tools needed — memory is transparent
  const result = streamText({
    model,
    messages,
    system: 'You are a helpful assistant.',
  });
  
  return result.toUIMessageStreamResponse();
}
```

**What happens automatically:**
1. On each request, NAMS retrieves memories relevant to the user's message
2. Memories are injected into the system prompt as context
3. After the model responds, the interaction is stored in short-term memory
4. Long-term facts are extracted and persisted to the Neo4j graph

**Memory scoping:**
- `userId` — Required. Groups all memories for this user
- `conversationId` — Optional. Pin to a specific conversation thread; if omitted, a new one is created

**API surface:**

```typescript
interface Nams {
  /**
   * Wrap an LLM with automatic memory. Memory retrieval + storage happens
   * transparently before and after each call.
   */
  wrap<T extends LanguageModel>(
    model: T,
    scope: { userId: string; conversationId?: string }
  ): LanguageModel;
  
  /**
   * Alternative: get query_memory + store_memory tools for manual control.
   */
  tools(scope: { userId: string; conversationId?: string }): {
    query_memory: Tool;
    store_memory: Tool;
  };
}
```

---

### Mode 2 — Custom Tools (Model-Driven Memory)

Get `query_memory` and `store_memory` as Vercel AI SDK tools. The model decides when to call them, giving you visibility into the memory process.

**Per-request usage:**

```typescript
// In app/api/chat/route.ts
import { createNams } from '@/lib/nams';
import { streamText, stepCountIs } from 'ai';
import { openai } from '@ai-sdk/openai';

export async function POST(req: Request) {
  const { messages, userId, conversationId } = await req.json();
  
  const nams = createNams({
    apiKey: process.env.MEMORY_API_KEY!,
    workspaceId: process.env.MEMORY_WORKSPACE_ID,
  });
  
  // Get memory tools — model decides when to call them
  const tools = nams.tools({
    userId,
    conversationId,
  });
  
  const result = streamText({
    model: openai('gpt-4o-mini'),
    messages,
    tools,
    system: SYSTEM_PROMPT,  // Must instruct the model to use memory
    stopWhen: stepCountIs(10),
  });
  
  return result.toUIMessageStreamResponse();
}
```

**System prompt (required):**

The model must be told when to use memory. Include these instructions:

```
You MUST follow this pattern on EVERY response:

1. FIRST: Call query_memory to retrieve relevant context about the user
2. THEN: Provide your answer using the retrieved memories
3. FINALLY: Call store_memory to save any new facts or preferences

Important: Always use memory tools, never skip any step.
```

See [lib/constants.ts](lib/constants.ts) for a complete example.

**Tool signatures:**

```typescript
// query_memory — Retrieve memories
tool<QueryInput, QueryOutput>({
  description: 'Search NAMS for context relevant to the current message. Call this FIRST every turn.',
  inputSchema: zodSchema({
    query: z.string().describe('Keywords or phrase to search'),
    limit: z.number().int().min(1).max(20).default(5),
  }),
  execute: async ({ query, limit }) => {
    // Returns: { found: boolean; count?: number; memories: MemoryHit[] }
  }
})

// store_memory — Persist information
tool<StoreInput, StoreOutput>({
  description: 'Persist important info to NAMS. Call this AFTER your response.',
  inputSchema: zodSchema({
    content: z.string().min(1).max(2000),
    type: z.enum(['fact', 'interaction', 'pattern', 'user_preference']),
    confidence: z.number().min(0).max(1).default(0.7),
    tags: z.array(z.string().max(40)).max(10).default([]),
  }),
  execute: async ({ content, type, confidence, tags }) => {
    // Returns: { stored: boolean; type: string; preview: string; message: string }
  }
})
```

**When to use custom tools:**
- You want to see memory operations in the reasoning trace
- You need to customize tool schemas or behavior
- You want fine-grained control over when memory is accessed
- You're integrating NAMS with agentic frameworks

---

                                                                                                                                                                                                                                                                                                                                                                                                               ## Memory Design

### Three Memory Layers

NAMS organizes memories across three cognitive types:

| Layer | Type | Storage | Search |
|-------|------|---------|--------|
| **Short-term** | Episodic (current conversation) | Per-conversation message thread | Vector + keyword search |
| **Long-term** | Semantic (extracted facts) | Neo4j graph entities (facts, preferences, patterns) | Graph traversal + entity search |
| **Reasoning** | Procedural (how decisions were made) | Per-step records (reasoning text, action, result) | List by conversation |

### Cross-Session Memory Retrieval

A key feature is **retrieving memories from previous conversations**. This requires passing a list of previous conversation IDs:

```typescript
// On first request, no previous conversations exist
const tools = nams.tools({ userId });

// After establishing a conversation, pass previousConversationIds
const tools = nams.tools({ 
  userId,
  conversationId: 'current-conv-123',
  previousConversationIds: ['prev-conv-1', 'prev-conv-2'], // from sidebar/session list
});
```

When `query_memory` is called, it searches in this order:
1. **Current conversation** (exact match)
2. **Previous conversations** (user-provided list)
3. **Long-term graph** (Neo4j facts, regardless of conversation)

This enables:
- ✅ "You told me last week you prefer coffee" — retrieved from previous conversation
- ✅ "You are a data scientist" — stored as a long-term fact across all conversations
- ✅ Cross-user isolation — each `userId` has separate memory space

                                                                                                                                                                                                                                                                                                                                                                                                               ### Memory Cycle (Model-Driven Mode)

When using **Custom Tools mode**, the system prompt enforces this sequence on every turn:

                                                                                                                                                                                                                                                                                                                                                                                                               ```
                                                                                                                                                                                                                                                                                                                                                                                                               STEP 1: query_memory   → retrieve context BEFORE answering
                                                                                                                                                                                                                                                                                                                                                                                                               STEP 2: answer         → respond using retrieved memories as grounding
                                                                                                                                                                                                                                                                                                                                                                                                               STEP 3: store_memory   → persist facts/preferences/interactions AFTER answering
                                                                                                                                                                                                                                                                                                                                                                                                               ```

This is **agent-directed** (not automatic): the LLM decides what's worth storing, assigns confidence levels, and classifies content (`fact` / `user_preference` / `interaction` / `pattern`).

**Note:** In **Provider mode**, this cycle happens transparently — no system prompt modifications needed.

                                                                                                                                                                                                                                                                                                                                                                                                               ---

---

### Transport Layer — REST API

NAMS doesn't connect directly to Neo4j. The [`@neo4j-labs/agent-memory`](https://www.npmjs.com/package/@neo4j-labs/agent-memory) SDK is a thin HTTPS REST client:

```
Your App  ──HTTPS POST──▶  https://memory.neo4jlabs.com/v1/<method>  ──▶  Neo4j AuraDB
                            (with MEMORY_API_KEY header)
```

This means:
- ✅ No direct database credentials in your app
- ✅ No local Neo4j setup required
- ✅ Managed infrastructure (automatic backups, scaling)
- ✅ Enterprise support available

Each operation (`query`, `store`, `list`) becomes a separate REST request. The client handles retries and error handling.

                                                                                                                                                                                                                                                                                                                                                                                                                     ---

---

## Prerequisites

| Requirement | Version | Get it |
|-------------|---------|--------|
| **Node.js** | ≥ 18 | [nodejs.org](https://nodejs.org) |
| **npm** | ≥ 9 | Bundled with Node 18+ |
| **NAMS API key** | — | Free at [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| **OpenAI API key** | — | Create at [platform.openai.com](https://platform.openai.com) |

**Why Node 18?**
- Required for `crypto.randomUUID()` (native)
- Required for `fetch` (native, no polyfill needed)
- Full ES2022 module support

No local Neo4j setup required — NAMS is a managed service.

                                                                                                                                                                                                                                                                                                                                                                                                                     ---

                                                                                                                                                                                                                                                                                                                                                                                                                     ## Setup

                                                                                                                                                                                                                                                                                                                                                                                                                     ### 1. Clone and install dependencies

                                                                                                                                                                                                                                                                                                                                                                                                                     ```bash
                                                                                                                                                                                                                                                                                                                                                                                                                     git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
                                                                                                                                                                                                                                                                                                                                                                                                                     cd neo4j-agent-integrations/vercel-agent/vercel_Nams
                                                                                                                                                                                                                                                                                                                                                                                                                     npm install
                                                                                                                                                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                                                                                                                                                     ### 2. Configure environment variables

Copy the example and fill in your secrets:

                                                                                                                                                                                                                                                                                                                                                                                                                     ```bash
cp .env.local.example .env.local
                                                                                                                                                                                                                                                                                                                                                                                                                     ```

Edit `.env.local`:

                                                                                                                                                                                                                                                                                                                                                                                                                     ```env
# REQUIRED

Your NAMS API key (free account at https://memory.neo4jlabs.com)
MEMORY_API_KEY=sk-nams-...

Your OpenAI API key (https://platform.openai.com)
OPENAI_API_KEY=sk-proj-...

# OPTIONAL

Which integration mode? "provider" (recommended) or "tools"
NAMS_MODE=provider

Pin to a specific NAMS workspace (omit for default)
MEMORY_WORKSPACE_ID=workspace-123

Override NAMS endpoint (rarely needed)
MEMORY_ENDPOINT=https://memory.neo4jlabs.com/v1

Which OpenAI model? (default: gpt-4o-mini)
OPENAI_MODEL=gpt-4o
                                                                                                                                                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                                                                                                                                                     ---

                                                                                                                                                                                                                                                                                                                                                                                                                     ## Running

                                                                                                                                                                                                                                                                                                                                                                                                                     ```bash
                                                                                                                                                                                                                                                                                                                                                                                                                     npm run dev
                                                                                                                                                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                                                                                                                                                     Open [http://localhost:3000](http://localhost:3000).

                                                                                                                                                                                                                                                                                                                                                                                                                     The app starts with four built-in suggestion prompts to illustrate the memory cycle. Click one or type your own message.

                                                                                                                                                                                                                                                                                                                                                                                                                     ### Production build

                                                                                                                                                                                                                                                                                                                                                                                                                     ```bash
                                                                                                                                                                                                                                                                                                                                                                                                                     npm run build
                                                                                                                                                                                                                                                                                                                                                                                                                     npm start
                                                                                                                                                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                                                                                                                                                     ---

                                                                                                                                                                                                                                                                                                                                                                                                                     ## Project structure

                                                                                                                                                                                                                                                                                                                                                                                                                     ```
                                                                                                                                                                                                                                                                                                                                                                                                                     vercel_Nams/
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── app/
                                                                                                                                                                                                                                                                                                                                                                                                                     │   ├── api/
                                                                                                                                                                                                                                                                                                                                                                                                                     │   │   ├── chat/route.ts          # POST /api/chat — main agent endpoint
                                                                                                                                                                                                                                                                                                                                                                                                                     │   │   └── reasoning/route.ts     # GET  /api/reasoning — fetch stored steps
                                                                                                                                                                                                                                                                                                                                                                                                                     │   ├── globals.css
                                                                                                                                                                                                                                                                                                                                                                                                                     │   ├── layout.tsx
                                                                                                                                                                                                                                                                                                                                                                                                                     │   └── page.tsx                   # Root page — wires AppHeader + ChatComponent
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── components/
                                                                                                                                                                                                                                                                                                                                                                                                                     │   ├── AppHeader.tsx              # Top bar with dark/light toggle
                                                                                                                                                                                                                                                                                                                                                                                                                     │   └── chat/
                                                                                                                                                                                                                                                                                                                                                                                                                     │       ├── ChatComponent.tsx      # Chat UI — useChat, tool-call display, panels
                                                                                                                                                                                                                                                                                                                                                                                                                     │       ├── MemoryPanel.tsx        # Collapsible panel: recent / observations / reasoning tabs
                                                                                                                                                                                                                                                                                                                                                                                                                     │       ├── ReasoningPanel.tsx     # Per-message reasoning step trace
                                                                                                                                                                                                                                                                                                                                                                                                                     │       └── styles.ts              # Shared inline style helpers
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── lib/
                                                                                                                                                                                                                                                                                                                                                                                                                     │   ├── constants.ts               # SYSTEM_PROMPT (mandatory query→answer→store)
                                                                                                                                                                                                                                                                                                                                                                                                                     │   └── nams-memory-provider.ts    # NAMS client, tools, conversation helpers
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── types/
                                                                                                                                                                                                                                                                                                                                                                                                                     │   └── index.ts                   # Shared TypeScript types (MemoryHit, ReasoningStep, …)
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── utils/
                                                                                                                                                                                                                                                                                                                                                                                                                     │   └── message.ts                 # getMsgText, parseMemory, formatErrorMessage helpers
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── constants.ts                   # DEFAULT_SUGGESTIONS, SESSION_STORAGE_KEY
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── declarations.d.ts              # Module augmentations / ambient declarations
                                                                                                                                                                                                                                                                                                                                                                                                                     ├── .env.local.example
                                                                                                                                                                                                                                                                                                                                                                                                                     └── package.json
                                                                                                                                                                                                                                                                                                                                                                                                                     ```

                                                                                                                                                                                                                                                                                                                                                                                                                     ---

### 3. Run the dev server

```bash
npm run dev
# Server runs on http://localhost:3000
```

---

## Project Structure

```
vercel_Nams/
│
├── lib/nams/                    # NAMS integration (reusable)
│   ├── index.ts                 # createNams() entry point
│   ├── provider.ts              # Provider mode (wrap models)
│   ├── tools.ts                 # Tools mode (query/store functions)
│   ├── client.ts                # NAMS API client helpers
│   └── extract.ts               # Graph extraction logic
│
├── lib/
│   ├── nams-memory-provider.ts  # Legacy compatibility (imports from lib/nams)
│   ├── nams-provider.ts         # High-level wrapper
│   └── constants.ts             # SYSTEM_PROMPT, defaults
│
├── app/api/chat/route.ts        # Agentic chat endpoint
├── app/page.tsx                 # UI entry point
│
├── components/
│   ├── chat/
│   │   ├── ChatComponent.tsx    # Main chat UI (uses useChat)
│   │   ├── MemoryPanel.tsx      # Display retrieved memories
│   │   └── ReasoningPanel.tsx   # Show tool calls & reasoning
│   └── ... (other UI components)
│
├── types/
│   └── *.ts                     # TypeScript types (MemoryHit, etc.)
│
├── .env.local.example
├── package.json
└── README.md
```

---

## Extracting NAMS for Your Project

### Copy these files

To use NAMS in another Next.js project, copy the `lib/nams/` folder:

```bash
# From neo4j-agent-integrations/vercel-agent/vercel_Nams
cp -r lib/nams /path/to/your-project/lib/
```

### Install dependencies

```bash
npm install @neo4j-labs/agent-memory ai zod
```

### Use in your API route

```typescript
// your-project/app/api/chat/route.ts
import { createNams } from '@/lib/nams';
import { streamText, stepCountIs } from 'ai';
import { openai } from '@ai-sdk/openai';

export async function POST(req: Request) {
  const { messages, userId } = await req.json();
  
  const nams = createNams({
    apiKey: process.env.MEMORY_API_KEY!,
  });
  
  // Choose your mode
  const mode = process.env.NAMS_MODE || 'provider';
  
  if (mode === 'provider') {
    const model = nams.wrap(openai('gpt-4o-mini'), { userId });
    return streamText({ model, messages }).toUIMessageStreamResponse();
  } else {
    const tools = nams.tools({ userId });
    return streamText({
      model: openai('gpt-4o-mini'),
      messages,
      tools,
      system: 'Query memory first, then answer, then store.',
      stopWhen: stepCountIs(10),
    }).toUIMessageStreamResponse();
  }
}
```

---

## Core Files Explained

### `lib/nams/index.ts`

Entry point. Exports `createNams(config)` which returns an object with:
- `wrap(model, scope)` — Provider mode (automatic memory)
- `tools(scope)` — Tools mode (model-driven memory)

### `lib/nams/provider.ts`

Implements the Provider mode using `wrapLanguageModel` middleware. Automatically:
1. Retrieves memories before each call
2. Injects them into the system prompt
3. Stores the turn after each call

### `lib/nams/tools.ts`

Implements the Tools mode. Returns `{ query_memory, store_memory }` as Vercel AI SDK `tool()` objects:
- **query_memory**: Searches 4 sources in parallel
- **store_memory**: Routes by type to short-term or long-term storage

### `lib/nams/client.ts`

Low-level NAMS API helpers:
- `makeClient()` — Creates a MemoryClient instance
- `resolveConversation()` — Gets or creates conversation ID
- `retrieveMemories()` — Multi-source memory search
- `storeMemory()` — Persist facts/interactions

### `lib/nams/extract.ts`

Graph extraction using an LLM:
- Takes stored memories
- Extracts entities (facts, preferences, patterns)
- Stores to Neo4j as graph nodes

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MEMORY_API_KEY` | ✅ Yes | — | API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) |
| `OPENAI_API_KEY` | ✅ Yes | — | OpenAI API key |
| `NAMS_MODE` | No | `provider` | Integration mode: `provider` or `tools` |
| `MEMORY_WORKSPACE_ID` | No | _(default)_ | Pin to a specific NAMS workspace |
| `MEMORY_ENDPOINT` | No | `https://memory.neo4jlabs.com/v1` | Override NAMS API URL |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | LLM model ID |

                                                                                                                                                                                                                                                                                                                                                                                                                                       ---

                                                                                                                                                                                                                                                                                                                                                                                                                                       ## Dependencies

                                                                                                                                                                                                                                                                                                                                                                                                                                       | Package | Role |
                                                                                                                                                                                                                                                                                                                                                                                                                                       |---------|------|
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `ai` (Vercel AI SDK) | `streamText`, `tool`, `useChat`, `createUIMessageStream` |
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `@ai-sdk/openai` | OpenAI provider for the Vercel AI SDK |
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `@ai-sdk/react` | `useChat` React hook |
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `@neo4j-labs/agent-memory` | NAMS `MemoryClient` — short-term, long-term, reasoning APIs |
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `@neo4j-ndl/react` | Neo4j Design Language UI components |
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `zod` | Input schema validation for the memory tools |
                                                                                                                                                                                                                                                                                                                                                                                                                                       | `next` | App framework and API routes |

                                                                                                                                                                                                                                                                                                                                                                                                                                       ---

## How to Use NAMS in Your Projects

### With Provider Mode

This is the **simplest approach** — memory is automatic.

```typescript
// 1. Create once (e.g., lib/nams.ts)
import { createNams } from '@ai-sdk/generative';
export const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });

// 2. Use in API route (app/api/chat/route.ts)
import { streamText } from 'ai';
import { openai } from '@ai-sdk/openai';
import { nams } from '@/lib/nams';

export async function POST(req: Request) {
  const { messages, userId } = await req.json();
  
  // Wrap the model — NAMS handles memory automatically
  const model = nams.wrap(openai('gpt-4o-mini'), { userId });
  
  return streamText({ model, messages }).toUIMessageStreamResponse();
}
```

### With Custom Tools Mode

Use this when you want **fine-grained control** over memory operations.

```typescript
// In your API route (app/api/chat/route.ts)
import { streamText, stepCountIs } from 'ai';
import { openai } from '@ai-sdk/openai';
import { createNams } from '@ai-sdk/generative';
import { SYSTEM_PROMPT } from '@/lib/constants';

export async function POST(req: Request) {
  const { messages, userId, conversationId } = await req.json();
  
  const nams = createNams({ apiKey: process.env.MEMORY_API_KEY! });
  const tools = nams.tools({ userId, conversationId });
  
  return streamText({
    model: openai('gpt-4o-mini'),
    messages,
    tools,
    system: SYSTEM_PROMPT,
    stopWhen: stepCountIs(10),
  }).toUIMessageStreamResponse();
}
```

**Key differences:**
- **Provider**: No system prompt changes needed, no tool traces visible
- **Tools**: Requires system prompt, tool calls visible in logs/UI

---

## Troubleshooting

### Memory not persisting

**Problem:** Facts from one conversation don't appear in the next session.

**Solutions:**
1. Check `.env.local` has `MEMORY_API_KEY` and `OPENAI_API_KEY`
2. Verify `userId` stays consistent across sessions (check browser localStorage `nams-session-id`)
3. In **tools mode**: ensure system prompt includes all 3 steps (query → answer → store)
4. Check server logs for `[NAMS:store]` messages confirming facts are saved
5. Test with `/api/reasoning?userId=<id>` endpoint to see stored reasoning

### Model never calls memory tools (tools mode)

**Problem:** Model ignores `query_memory` and `store_memory` tools.

**Solutions:**
1. Verify `NAMS_MODE=tools` in `.env.local`
2. Check `SYSTEM_PROMPT` contains clear instructions: "FIRST call query_memory, THEN answer, THEN call store_memory"
3. Increase token budget: use `gpt-4-turbo` instead of `gpt-4o-mini`
4. Check server logs to confirm tools are registered

### Errors connecting to NAMS API

**Problem:** "MEMORY_API_KEY is not set" or HTTP 503 errors.

**Solutions:**
1. Generate a free API key at [memory.neo4jlabs.com](https://memory.neo4jlabs.com)
2. Copy it to `.env.local`: `MEMORY_API_KEY=sk-nams-...`
3. Restart dev server: `npm run dev`

---

## Best Practices

### 1. Use Provider Mode by Default
- Simpler, no system prompt needed
- Automatically handles memory every turn
- Switch to Tools mode only if you need visible memory traces

### 2. Scope Users Correctly
```typescript
// Good: each user gets separate memory
nams.wrap(model, { userId: req.user.id })

// Bad: everyone shares the same memory
nams.wrap(model, { userId: 'default' })
```

### 3. Handle Long Conversations
Memory accumulates! Consider:
- Archive old conversations after X days
- Summarize long conversations into facts
- Manually prune old memories via NAMS API

### 4. Monitor API Costs
- Each `query_memory` → 1 REST call
- Each `store_memory` → 1 REST call
- Use `stopWhen: stepCountIs(10)` to prevent runaway loops

---

## Resources

- **NAMS API**: [memory.neo4jlabs.com](https://memory.neo4jlabs.com)
- **Vercel AI SDK**: [ai-sdk.dev/docs/agents/memory](https://ai-sdk.dev/docs/agents/memory)
- **This repo**: [github.com/neo4j-labs/neo4j-agent-integrations](https://github.com/neo4j-labs/neo4j-agent-integrations)

---

**Next steps**: Copy `lib/nams/` to your project and start building! 🚀
                                                                                                                                                                                                                                                                                                                                                                                                                                       