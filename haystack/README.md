# Haystack + Neo4j Integration

## Overview

**Haystack** is an open-source framework by deepset for building LLM applications from composable
components: `Pipeline`s for fixed flows, and `Agent`s that choose tools at run time. All examples here
target **Haystack 3.0**.

**Official Resources:**
- Website: https://haystack.deepset.ai
- Documentation: https://docs.haystack.deepset.ai/
- Neo4j Integration: https://haystack.deepset.ai/integrations/neo4j-document-store

This folder shows two ways to connect Haystack to Neo4j, one notebook each:

| | [1. Neo4j MCP server](#1-neo4j-mcp-server) | [2. GraphRAG retrievers](#2-graphrag-retrievers) |
| --- | --- | --- |
| **Notebook** | [`neo4j_mcp_haystack.ipynb`](./neo4j_mcp_haystack.ipynb) | [`neo4j_graphrag_haystack.ipynb`](./neo4j_graphrag_haystack.ipynb) |
| **Graph access** | MCP tools: `get-schema`, `read-cypher` | `neo4j-graphrag` retrievers |
| **Retrieval** | Cypher the agent writes after reading the schema | Vector, hybrid, and graph traversal (`retrieval_query`) |
| **Needs an index?** | No | Yes, vector + full-text |
| **Haystack pattern** | `Agent` + `MCPToolset` | `Agent` + retrievers as `Tool`s |
| **Database** | Public demo (`companies`), read-only | Public demo (`companies`), read-only |
| **Needs** | OpenAI API key | OpenAI API key |

**Which one to use:**
- Use **MCP** for questions about structure and relationships: counts, paths, "who invested in whom".
- Use **GraphRAG** to search unstructured text that is already indexed, when results need to carry
  graph context and checkable citations.

---

## 1. Neo4j MCP server

**Notebook:** [`neo4j_mcp_haystack.ipynb`](./neo4j_mcp_haystack.ipynb)

A Haystack agent talks to Neo4j through the official
[Neo4j MCP server](https://neo4j.com/docs/mcp/current/). The agent calls named tools such as
`get-schema` and `read-cypher` instead of opening a database connection itself. Haystack's
`mcp-haystack` integration loads those tools directly, so there is no retriever code and no index to
maintain.

### What the notebook does

1. Starts the Neo4j MCP server in HTTP mode.
2. Sends Neo4j credentials as a per-request `Authorization` header, not as server environment
   variables.
3. Lists the available tools with a direct JSON-RPC call before involving an LLM.
4. Builds a Haystack `Agent` with `MCPToolset` and runs example questions.
5. Adds a custom Haystack `Tool` (`get_investments`) alongside the MCP tools.
6. Shuts the server down cleanly.

### Security choices

- `NEO4J_READ_ONLY=true`, so `write-cypher` is never advertised to the agent.
- A Haystack-side allow-list: `tool_names=["get-schema", "read-cypher"]`.
- A schema-first system prompt, so the model reads labels and properties instead of guessing them.

### Installation

```bash
pip install "haystack-ai>=3.0" mcp-haystack neo4j-mcp-server neo4j python-dotenv
```

### Key code

`MCPToolset` loads the MCP server's tools into Haystack, and the agent uses them like any other tool:

```python
mcp_tools = MCPToolset(
    server_info=StreamableHttpServerInfo(url=MCP_URL, headers=AUTH_HEADERS),
    tool_names=["get-schema", "read-cypher"],   # allow-list
)

graph_agent = Agent(chat_generator=OpenAIChatGenerator(model=OPENAI_MODEL), tools=mcp_tools)
```

See the notebook for starting the server and building the auth header.

> In HTTP mode the MCP server rejects `NEO4J_USERNAME` / `NEO4J_PASSWORD` at startup, so the notebook
> removes them from the server's environment before launching it.

---

## 2. GraphRAG retrievers

**Notebook:** [`neo4j_graphrag_haystack.ipynb`](./neo4j_graphrag_haystack.ipynb)

Uses Neo4j's official retrieval library,
[`neo4j-graphrag`](https://neo4j.com/docs/neo4j-graphrag-python/current/), with Haystack. The
retrievers are called directly (`retriever.search()`) inside plain functions, and those functions
become Haystack `Tool`s for an `Agent`. No custom Haystack component is needed.

The demo `companies` graph splits news articles into `Chunk` nodes, linked to the organizations they
mention:

```
(Article)-[:HAS_CHUNK]->(Chunk)
(Article)-[:MENTIONS]->(Organization)
(Organization)-[:HAS_COMPETITOR|HAS_INVESTOR|HAS_SUPPLIER]->(Organization)
```

### What it covers

| Retriever | What it does |
| --- | --- |
| `VectorRetriever` | Semantic search over chunk text |
| `VectorCypherRetriever` | Semantic search, then a `retrieval_query` walks to the article, its date and sentiment, the companies mentioned, and their competitors |
| `HybridRetriever` | Vector + full-text search combined; recovers exact names, tickers, and product codes |
| `HybridCypherRetriever` | Hybrid search plus the same graph traversal |

It also covers:

- **Pairing the embedding model with the index.** The notebook uses `news_sbert` (384 dims) with
  `SentenceTransformerEmbeddings`, which runs locally with no key. A mismatched model returns
  meaningless results without raising an error.
- **Checkable citations.** Each graph result carries an `article_id`. The notebook looks that
  `Article` up and confirms the retrieved passage is one of its chunks.
- **An agent that picks a retriever.** Retrievers are wrapped as `Tool`s, and the tool
  descriptions decide which one the agent calls.
- **A side-by-side comparison** of the retrieval strategies on a single query.

### Installation

```bash
pip install "haystack-ai>=3.0" neo4j-graphrag neo4j sentence-transformers python-dotenv
```

### Key code

Each retriever is called directly inside a plain function, and that function becomes a Haystack `Tool`:

```python
def search_news_with_context(question: str) -> str:
    """Search news and return the source article, date, sentiment, and companies mentioned."""
    result = hybrid_graph_retriever.search(query_text=question, top_k=5)
    return json.dumps([json.loads(item.content) for item in result.items])

news_analyst = Agent(
    chat_generator=OpenAIChatGenerator(model=OPENAI_MODEL),
    tools=[_tool(search_news_with_context, search_news_with_context.__doc__), ...],
)
```

See the notebook for the retriever setup, the `retrieval_query`, and the `_tool` helper.

> **Cypher 25:** `neo4j-graphrag` generates vector queries with the Cypher 25 `SEARCH` clause.
> The demo database defaults to Cypher 5, so the notebook prefixes those queries with `CYPHER 25`.
> Skip that cell if your database already defaults to Cypher 25.

---

## Configuration

Both notebooks read the OpenAI key from `haystack/.env` with `python-dotenv`. The file is covered by
`.gitignore`.

```bash
OPENAI_API_KEY=sk-...
```

Both use the public demo database, which needs no credentials of your own:
- URI: `neo4j+s://demo.neo4jlabs.com`
- Database: `companies`
- Username / password: `companies` / `companies`

## Roadmap

[`neo4j_heystack_integration_plan.md`](./neo4j_heystack_integration_plan.md) describes the plan to
combine these approaches into one `Neo4jGraphAgent`. It would put MCP tools and GraphRAG retrievers
on the same agent, enable retrievers only when the matching indexes exist, and add Haystack 3.0
Skills, Hooks, async execution, and Neo4j agent memory.

## Resources

- **Haystack**: https://haystack.deepset.ai/
- **Haystack Agents**: https://docs.haystack.deepset.ai/docs/agents
- **`mcp-haystack` reference**: https://docs.haystack.deepset.ai/reference/integrations-mcp
- **Neo4j MCP docs**: https://neo4j.com/docs/mcp/current/
- **neo4j-graphrag for Python**: https://neo4j.com/docs/neo4j-graphrag-python/current/
- **Neo4j + Haystack developer page**: https://neo4j.com/developer/genai-ecosystem/haystack/

## Status

- MCP-based Haystack agent, read-only, with a custom tool alongside the MCP tools
- GraphRAG retrievers (`neo4j-graphrag`) as Haystack agent tools, with checkable citations
- Combined `Neo4jGraphAgent`: see [Roadmap](#roadmap)
