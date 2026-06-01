# Vercel AI SDK + Neo4j Agent Memory — Next.js Full-Stack Demo

A production-ready Next.js application demonstrating streaming chat with **Vercel AI SDK v5** + **Neo4j Agent Memory Service (NAMS)**, featuring persistent research insights and real-time Neo4j entity search.

## Features

- **Streaming Chat UI** — Real-time AI responses with Vercel AI SDK v5
- **Neo4j Knowledge Graph** — Query organizations, industries, locations from a live knowledge graph
- **Persistent Memory via NAMS** — Save research findings to [Neo4j Agent Memory Service](https://memory.neo4jlabs.com) for future context
- **Provider-Agnostic** — Swap between OpenAI, Google Gemini, or other LLMs with env vars
- **Type-Safe** — Full TypeScript + Zod validation for API payloads
- **Production-Ready** — Next.js 15, React 18, proper error handling

## Quick Start

### 1. Clone and Install

```bash
cd vercel-agent/next-js-demo
npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env.local`:

```bash
cp .env.example .env.local
```

Then set your **AI API key** (choose one):

```env
# OpenAI (default)
OPENAI_API_KEY="sk-..."

# OR Google Gemini
# GOOGLE_GENERATIVE_AI_API_KEY="AIza..."
```

### 3. (Optional) Configure Neo4j Agent Memory Service

To enable persistent memory, get a free API key from [memory.neo4jlabs.com](https://memory.neo4jlabs.com) and set:

```env
MEMORY_API_KEY="nams_..."
```

**Without memory config:** The app still works — memory features degrade gracefully.

### 4. Run Dev Server

```bash
npm run dev
```

Open http://localhost:3000 in your browser.

## Architecture

### App Structure

```
app/
  page.tsx                    # Chat UI component
  api/
    chat/route.ts             # API routes: GET (status), POST (chat), PUT (save memory)
lib/
  memoryService.ts            # NAMS MemoryClient singleton + conversation management
package.json                  # Dependencies (ai@5, @ai-sdk/openai@2, @neo4j-labs/agent-memory)
```

### API Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/chat` | Returns model + memory config status |
| `POST` | `/api/chat` | Streams chat response with Neo4j tool calls + NAMS context |
| `PUT` | `/api/chat` | Saves a finding to NAMS long-term memory (Zod-validated) |

### Memory Architecture

This demo uses **Neo4j Agent Memory Service (NAMS)** — a hosted REST service at `https://memory.neo4jlabs.com/v1`, accessed via the `@neo4j-labs/agent-memory` npm package. It is **not** a direct Neo4j connection — no Neo4j credentials are needed for memory.

```
Vercel AI SDK agent
       │
       ├── shortTerm.getContext(conversationId)    ← retrieves recent messages + reflections
       ├── longTerm.searchEntities(query)          ← semantic search over stored facts
       ├── shortTerm.addMessage(conversationId, …) ← persists each chat turn
       └── longTerm.addEntity(name, type, {desc})  ← stores research findings
              │
       NAMS REST API (memory.neo4jlabs.com/v1)
```

## How It Works

### 1. User Submits Query

```
User: "Show me tech companies in California"
```

### 2. Memory Retrieval (if NAMS configured)

Before calling the LLM, the API retrieves prior context:
- `shortTerm.getContext(conversationId)` — recent conversation + reflections
- `longTerm.searchEntities(userQuery)` — semantically similar stored facts

This context is injected into the system prompt.

### 3. Streaming Chat Response

The API uses `streamText()` with `stopWhen: stepCountIs(6)` and two tools:

#### Tool: `query_neo4j`
Searches the live Neo4j demo database for organizations.

```typescript
tools: {
  query_neo4j: tool({
    description: 'Search organizations in the Neo4j companies knowledge graph',
    inputSchema: z.object({ query: z.string().min(2) }),
    execute: async ({ query }) => {
      // Runs Cypher: MATCH (org:Organization) WHERE org.name CONTAINS $query
      // Returns matching organizations with name, summary, industry
    },
  }),
  save_learning: tool({
    description: 'Save important findings to NAMS long-term memory',
    inputSchema: z.object({
      title: z.string().min(4),
      content: z.string().min(8),
      kind: z.enum(['semantic', 'procedural', 'episodic']),
    }),
    execute: async ({ title, content, kind }) => {
      // Calls memoryClient.longTerm.addEntity(title, entityType, { description })
    },
  }),
}
```

### 4. Message Persistence

After each chat turn, messages are persisted to NAMS via `shortTerm.addMessage()` so future sessions have context.

## Database Schema

### Neo4j Demo Database (Public, Read-Only)

```
URI:      neo4j+s://demo.neo4jlabs.com:7687
Username: companies
Password: companies
Database: companies
```

Dataset: 250k entities from Diffbot's knowledge graph.

- `(Organization)` — name, summary, industry, location
- `(Article)` — mentioning orgs + industries
- Vector embeddings on article chunks

```cypher
-- Example query run by the tool:
MATCH (org:Organization)
WHERE org.name CONTAINS $query OR org.summary CONTAINS $query
RETURN org.name AS name, org.summary AS summary, org.industry AS industry
LIMIT 5
```

### Neo4j Agent Memory Service (NAMS)

NAMS is a hosted REST service — **no Neo4j instance to manage**. Authenticate with `MEMORY_API_KEY` only.

Memory is organized into:
- **Short-term**: conversation turns, reflections, recent observations
- **Long-term**: named entities (people, organizations, concepts, custom)

Valid entity types for `longTerm.addEntity()`: `person`, `organization`, `location`, `concept`, `tool`, `custom`.

## Configuration Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key (required if not using Google) |
| `GOOGLE_GENERATIVE_AI_API_KEY` | — | Google Gemini API key |
| `AI_MODEL` | `gpt-4o-mini` / `gemini-2.5-flash` | Override model name |
| `AI_PROVIDER` | auto-detected | Force provider: `openai` or `google` |
| `NEO4J_URI` | `neo4j+s://demo.neo4jlabs.com:7687` | Knowledge graph URI |
| `NEO4J_USERNAME` | `companies` | Knowledge graph username |
| `NEO4J_PASSWORD` | `companies` | Knowledge graph password |
| `NEO4J_DATABASE` | `companies` | Knowledge graph database |
| `MEMORY_API_KEY` | — | NAMS API key from memory.neo4jlabs.com (optional) |
| `MEMORY_ENDPOINT` | `https://memory.neo4jlabs.com/v1` | NAMS endpoint override |
| `DEMO_AGENT_ID` | `vercel-neo4j-research-agent` | Agent identifier (userId in NAMS) |

> **Note:** The old `MEMORY_NEO4J_URI/USERNAME/PASSWORD` env vars are no longer used. Memory now connects to the NAMS hosted REST service via `MEMORY_API_KEY`.

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `ai` | `^5.0.44` | Vercel AI SDK core (`streamText`, `tool`, `stepCountIs`) |
| `@ai-sdk/openai` | `^2.0.0` | OpenAI provider (spec v2 required by `ai@5`) |
| `@ai-sdk/google` | `^2.0.0` | Google Gemini provider |
| `@ai-sdk/react` | `^2.0.44` | React hooks (`useChat`) |
| `@neo4j-labs/agent-memory` | `^0.4.0` | NAMS client (`MemoryClient`) |
| `neo4j-driver` | `^5.28.0` | Neo4j knowledge graph driver |
| `next` | `^15.1.0` | Next.js framework |
| `zod` | `^3.25.76` | Schema validation |

## Usage Examples

### Example 1: Query Without Memory

1. Open http://localhost:3000
2. Type: `"What industries have the most organizations?"`
3. Watch streaming response with Neo4j data

### Example 2: Save and Reuse Findings

1. After getting a response, click **"Save Last Answer To Memory"**
2. Confirm saved ✓
3. Ask a follow-up: `"Build on that research"`
4. Prior context auto-injected via NAMS short-term + long-term memory

## Testing

### Unit Tests

```bash
npm test
```

### Manual curl Testing

**1. Check status:**
```bash
curl http://localhost:3000/api/chat
# Returns: { ok: true, modelProvider: "openai", modelName: "gpt-4o-mini", memoryEnabled: true, ... }
```

**2. Stream a chat message:**
```bash
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{
      "id": "1",
      "role": "user",
      "content": "Find Apple in the Neo4j database",
      "parts": [{"type": "text", "text": "Find Apple in the Neo4j database"}]
    }]
  }'
# Streams SSE: tool calls, text-delta chunks, finish
```

> **Note:** AI SDK v5 uses `UIMessage` format — messages must include a `parts` array alongside `content`.

**3. Save a memory (requires MEMORY_API_KEY):**
```bash
curl -X PUT http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"title": "Apple findings", "content": "Apple has subsidiaries in Japan and UK", "kind": "semantic"}'
# Returns: { ok: true, result: { id: "...", name: "Apple findings" } }
```

## Deployment

### Vercel (Recommended)

```bash
npm install -g vercel
vercel
```

Set env vars in Vercel dashboard under **Settings > Environment Variables**.

### Docker

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
```

```bash
docker build -t vercel-neo4j-demo .
docker run -p 3000:3000 \
  -e OPENAI_API_KEY=sk-... \
  -e MEMORY_API_KEY=nams_... \
  vercel-neo4j-demo
```

## Troubleshooting

### "No model provider configured"

Set either `OPENAI_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY` in `.env.local`.

### Memory features disabled / `memoryEnabled: false`

Memory is optional. Set `MEMORY_API_KEY` in `.env.local` to enable. Without it the chat still works.

### `"Unsupported model version v1 for provider openai.chat"`

You have an old `@ai-sdk/openai@1.x` installed. Run:
```bash
npm install @ai-sdk/openai@^2.0.0
```

### Agent responds after tool calls only (no text generation)

This was a bug in the original code — `maxSteps` was removed in AI SDK v5. The fix is `stopWhen: stepCountIs(6)` which is already applied.

### `"UNABLE_TO_GET_ISSUER_CERT_LOCALLY"` (corporate proxy / Zscaler)

Node.js doesn't trust your corporate SSL proxy's CA. Export the cert and reference it:

```bash
# macOS with Zscaler:
security find-certificate -a -c "Zscaler" -p /Library/Keychains/System.keychain > zscaler-certs.pem
```

The npm scripts already include `NODE_EXTRA_CA_CERTS=./zscaler-certs.pem`. Place the file in the project root. It's gitignored (`*.pem` rule).

### `add_entity failed: type must be person, organization, location, concept, tool, or custom`

NAMS requires specific entity types. The `kind` values `semantic`/`procedural`/`episodic` are automatically mapped to `concept`/`custom` by the `toNamsEntityType()` helper in `route.ts`.

### `"Invalid payload"` on PUT /api/chat

Check the Zod schema in `app/api/chat/route.ts`:
- `title`: min 4 chars
- `content`: min 8 chars
- `kind`: one of `semantic`, `procedural`, `episodic`

### Neo4j connection errors

- The public demo DB is open — no IP restrictions
- Default credentials: `companies` / `companies` at `neo4j+s://demo.neo4jlabs.com:7687`
- For a custom Neo4j instance, set `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`

## Learn More

- [Vercel AI SDK v5 docs](https://sdk.vercel.ai)
- [AI SDK v5 Migration Guide](https://sdk.vercel.ai/docs/migration-guides/migration-guide-5-0)
- [Neo4j Agent Memory Service](https://memory.neo4jlabs.com)
- [`@neo4j-labs/agent-memory` on npm](https://www.npmjs.com/package/@neo4j-labs/agent-memory)
- [Next.js docs](https://nextjs.org)

## License

See [LICENSE](../../LICENSE) in parent repo.

---

**Built with:** Next.js 15 · Vercel AI SDK v5 · `@neo4j-labs/agent-memory` · Neo4j 5
