# Vercel AI SDK + Neo4j Agent Memory — Next.js Full-Stack Demo

A production-ready Next.js application demonstrating streaming chat with **Vercel AI SDK** + **Neo4j Agent Memory**, featuring persistent research insights and real-time Neo4j entity search.

## Features

- **Streaming Chat UI** — Real-time AI responses with Vercel AI SDK
- **Neo4j Knowledge Graph** — Query organizations, industries, locations from a live knowledge graph
- **Persistent Memory** — Save research findings to Neo4j Agent Memory for future context
- **Provider-Agnostic** — Swap between OpenAI, Google Gemini, or other LLMs with env vars
- **Type-Safe** — Full TypeScript + Zod validation for API payloads
- **Production-Ready** — Using Next.js 15, React 18, proper error handling

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

Then set your **AI API keys**:

```env
# Choose ONE:
OPENAI_API_KEY="sk-..."
# OR
GOOGLE_GENERATIVE_AI_API_KEY="AIza..."
```

### 3. (Optional) Configure Neo4j Memory

To enable persistent memory, configure a second Neo4j instance:

```env
MEMORY_NEO4J_URI="neo4j+s://your-auradb-instance:7687"
MEMORY_NEO4J_USERNAME="neo4j"
MEMORY_NEO4J_PASSWORD="..."
MEMORY_NEO4J_DATABASE="neo4j"
```

**Without memory config:** The app still works—you just won't see "Save to Memory" button.

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
    chat/route.ts            # Streaming API: GET (status), POST (chat), PUT (save memory)
lib/
  memoryService.ts           # Neo4j Agent Memory integration
package.json                 # Dependencies (ai, neo4j-driver, neo4j-agent-memory)
```

### API Routes

- **GET /api/chat** — Returns demo status (model, memory enabled, config source)
- **POST /api/chat** — Stream chat response with Neo4j search + memory context
- **PUT /api/chat** — Save a learning to Neo4j Agent Memory (Zod-validated)

## How It Works

### 1. User Submits Query

```
User: "Show me tech companies in California"
```

### 2. Memory Retrieval (Optional)

If memory is configured, the system retrieves prior relevant research from Neo4j Agent Memory using:
- Full-text search (prompt keywords)
- Tag-based filtering
- Vector embeddings (optional)

### 3. Streaming Chat Response

The API uses `streamText()` with two tools:

#### Tool: `query_neo4j`
Searches the live Neo4j demo database for organizations, then returns results inline.

```typescript
tools: {
  query_neo4j: tool({
    description: 'Search organizations...',
    inputSchema: z.object({ query: z.string().min(2) }),
    execute: async ({ query }) => {
      // Runs Cypher: MATCH (org:Organization) WHERE org.name CONTAINS $query
      // Returns matching organizations
    },
  }),
  save_learning: tool({
    description: 'Save finding to Neo4j Agent Memory...',
    // Calls memoryService.captureUsefulLearning()
  }),
}
```

### 4. UI Update

Messages stream in real-time (powered by `useChat` hook). User can then click **"Save to Memory"** to persist the response.

## Database Schema

### Neo4j Demo (Public, Read-Only)

Default: `neo4j+s://demo.neo4jlabs.com:7687`
- **Organizations** — Name, summary, industry, location
- **Articles** — Mentioning orgs + industries
- **Vector embeddings** on article chunks

```cypher
// Example query in the tool:
MATCH (org:Organization)
WHERE org.name CONTAINS "Tech"
RETURN org.name, org.industry LIMIT 5
```

### Neo4j Agent Memory (Your Instance, Read-Write)

Must be configured via `MEMORY_NEO4J_*` env vars.

**Indices (auto-created by `neo4j-agent-memory`):**
- `memoryEmbedding` (vector index for semantic search)
- `memoryText` (fulltext index for keyword search)

```cypher
// Example learning stored:
CREATE (m:MemoryNode {
  agentId: "vercel-neo4j-demo",
  title: "Research: Tech companies in California...",
  content: "...",
  kind: "semantic",
  tags: ["tech", "california"]
}) SET m.createdAt = datetime()
```

## Configuration Reference

| Env Var | Default | Description |
|---------|---------|-------------|
| `OPENAI_API_KEY` | — | OpenAI API key (required if not using Google) |
| `GOOGLE_GENERATIVE_AI_API_KEY` | — | Google Gemini API key |
| `AI_MODEL` | `gpt-4o-mini` or `gemini-2.5-flash` | Override model name |
| `AI_PROVIDER` | auto | Force provider: `openai` or `google` |
| `NEO4J_URI` | `neo4j+s://demo.neo4jlabs.com:7687` | Knowledge graph URI |
| `NEO4J_USERNAME` | `companies` | Knowledge graph username |
| `NEO4J_PASSWORD` | `companies` | Knowledge graph password |
| `NEO4J_DATABASE` | `companies` | Knowledge graph database |
| `MEMORY_NEO4J_URI` | — | Memory instance URI (optional) |
| `MEMORY_NEO4J_USERNAME` | — | Memory instance username |
| `MEMORY_NEO4J_PASSWORD` | — | Memory instance password |
| `MEMORY_NEO4J_DATABASE` | — | Memory instance database |
| `MEMORY_VECTOR_INDEX` | `memoryEmbedding` | Vector index name |
| `MEMORY_FULLTEXT_INDEX` | `memoryText` | Fulltext index name |
| `DEMO_AGENT_ID` | `vercel-neo4j-demo` | Agent identifier for memory |

## Usage Examples

### Example 1: Query Without Memory

1. Open http://localhost:3000
2. Click "Load Status" → See model selected
3. Type: `"What industries have the most organizations?"`
4. Watch streaming response with Neo4j data

### Example 2: Save and Reuse Findings

1. After getting a response, click **"Save to Memory"**
2. Confirm saved ✓
3. Ask a follow-up: `"Build on that research"`
4. Memory context is auto-injected into the system prompt
5. AI remembers prior research

### Example 3: Custom Neo4j Queries

Modify `app/api/chat/route.ts` to add custom Cypher queries:

```typescript
const result = await session.run(`
  MATCH (org:Organization)-[:LOCATED_IN]->(loc:Location {name: $location})
  MATCH (org)-[:IN_INDUSTRY]->(ind:Industry)
  RETURN org.name, ind.name, COUNT(*) as count
  ORDER BY count DESC
`, { location: userLocation });
```

## Testing

### Unit Tests (Memory Payload Validation)

```bash
npm test
```

### Manual Testing

1. **Verify model loads:**
   ```bash
   curl http://localhost:3000/api/chat
   # Should return: { ok: true, modelProvider: "openai", ... }
   ```

2. **Stream a chat message:**
   ```bash
   curl -X POST http://localhost:3000/api/chat \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "Test"}]}'
   # Should stream server-sent events
   ```

3. **Save a memory (if configured):**
   ```bash
   curl -X PUT http://localhost:3000/api/chat \
     -H "Content-Type: application/json" \
     -d '{
       "title": "Test Finding",
       "content": "This is a test insight",
       "kind": "semantic"
     }'
   # Should return: { ok: true, result: { ... } }
   ```

## Deployment

### Vercel (Recommended)

```bash
npm install -g vercel
vercel
```

Set env vars in Vercel dashboard under Settings > Environment Variables.

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
  -e MEMORY_NEO4J_URI=neo4j+s://... \
  vercel-neo4j-demo
```

## Troubleshooting

### "No model provider configured"

Set either `OPENAI_API_KEY` or `GOOGLE_GENERATIVE_AI_API_KEY`.

### Memory features disabled

Memory is optional. If `MEMORY_NEO4J_URI` is missing, memory features gracefully degrade—chat still works.

### "Invalid memory payload" on PUT

Check [Zod schema](./app/api/chat/route.ts). Requirements:
- `title`: min 1 char (trimmed)
- `content`: min 1 char (trimmed)
- `kind`: one of `semantic`, `procedural`, `episodic`
- `tags`: array of 2+ char strings, max 10

### Neo4j connection errors

- Verify firewall allows your IP to the Neo4j instance
- Check username/password are correct
- Ensure database name exists (default: `companies` for demo)

## Learn More

- [Vercel AI SDK docs](https://sdk.vercel.ai)
- [Neo4j Agent Memory](https://github.com/neo4j-field/neo4j-agent-memory)
- [Next.js docs](https://nextjs.org)

## License

See [../LICENSE](../../LICENSE) in parent repo.

---

**Built with:** Next.js 15 + Vercel AI SDK + Neo4j Agent Memory
