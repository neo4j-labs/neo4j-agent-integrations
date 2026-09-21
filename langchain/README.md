# LangChain + Neo4j Integration

## Overview

**LangChain** is a Python toolkit for building applications powered by large language models. It provides composable chains and agents, a vast integration ecosystem, memory and retrieval systems, and production essentials like callbacks, tracing, and evaluation tools.

**Installation:**
```bash
pip install langchain langchain-neo4j langchain-mcp-adapters
```

For the GraphRAG retrieval examples:
```bash
pip install langchain neo4j-graphrag neo4j
```

**Key Features:**
- Composable chains and ReAct-style agents
- Native Neo4j integrations via `langchain-neo4j` package
- MCP server support through `langchain-mcp-adapters`
- Custom tool creation with the `@tool` decorator
- Support for virtually every major LLM provider (OpenAI, Anthropic, Google, Cohere, Mistral, AWS Bedrock, Azure, and more)
- GraphRAG retrievers from `neo4j-graphrag` exposed as agent tools
- Hosted Neo4j Aura Agents callable over MCP as a sub-agent

## Examples

| Notebook | Description |
|----------|-------------|
| [langchain.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/langchain/langchain.ipynb) | Walkthrough of LangChain with Neo4j integration, including MCP server setup, custom tool creation, vector search, and query execution |
| [langchain_graphrag.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/langchain/langchain_graphrag.ipynb) | Walkthrough of using `neo4j-graphrag` with LangChain: pairing embedding models with vector indexes, vector, hybrid and graph-traversal retrievers, and exposing them as agent tools |
| [langchain_aura_agent.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/langchain/langchain_aura_agent.ipynb) | Walkthrough of connecting a hosted Neo4j Aura Agent to LangChain over MCP: machine-to-machine authentication, token caching, and combining the hosted agent with local tools |

## Extension Points

### 1. MCP Integration

LangChain supports MCP servers via the `langchain-mcp-adapters` package. Use `MultiServerMCPClient` to connect to MCP servers and retrieve tools.

- **Neo4j MCP Server:** Leverage `mcp-neo4j-cypher` for schema reading and Cypher query execution

### 2. Direct Neo4j Integrations

The `langchain-neo4j` package provides native integrations for more control:

- **Neo4jGraph:** Direct connection to Neo4j for executing Cypher queries within custom tools
- **Neo4jVector:** Vector store integration for semantic search over graph data with support for hybrid search and custom retrieval queries

### 3. Custom Tools/Functions

Define custom Neo4j tools using the `@tool` decorator:

- Specify tool name and description via docstrings
- Implement functions that execute Cypher queries via `Neo4jGraph` or `Neo4jVector`
- Return results as structured JSON
- Combine MCP tools with custom tools in a single agent

### 4. Neo4j Checkpoint Savers

The `langchain-neo4j` package provides checkpoint savers for persisting agent state to Neo4j:

- **Neo4jSaver:** Synchronous checkpointer for storing conversation history and agent state
- **AsyncNeo4jSaver:** Async variant for non-blocking checkpoint operations

```python
from langgraph.checkpoint.neo4j import AsyncNeo4jSaver

async with await AsyncNeo4jSaver.from_conn_string(
    uri=NEO4J_URI,
    user=NEO4J_USERNAME,
    password=NEO4J_PASSWORD,
    database=NEO4J_DATABASE
) as checkpointer:
    await checkpointer.setup()

    agent = create_agent(
        model,
        tools,
        system_prompt=prompt,
        checkpointer=checkpointer,
    )
```

### 5. GraphRAG Retrievers

The `neo4j-graphrag` package provides retrievers that combine vector search with graph traversal. They are plain Python objects with a `search()` method, so they wrap with the `@tool` decorator like any other function:

- **VectorRetriever:** Semantic search over embedded text
- **VectorCypherRetriever:** Vector search followed by a `retrieval_query` that traverses outward from each match, so retrieved text arrives with its source article, dates, and related entities
- **HybridRetriever / HybridCypherRetriever:** Vector and full-text search merged, recovering exact matches on names and tickers that embeddings miss

```python
from neo4j_graphrag.retrievers import HybridCypherRetriever

# `node` and `score` are in scope: continue into the graph from each vector hit.
RETRIEVAL_QUERY = """
WITH node AS chunk, score
MATCH (article:Article)-[:HAS_CHUNK]->(chunk)
OPTIONAL MATCH (article)-[:MENTIONS]->(org:Organization)
RETURN chunk.text AS text, article.title AS title,
       collect(DISTINCT org.name)[..5] AS companies, score
"""

retriever = HybridCypherRetriever(
    driver=driver,
    vector_index_name="news",
    fulltext_index_name="news_fulltext",
    retrieval_query=RETRIEVAL_QUERY,
    embedder=OpenAIEmbeddings(),
)

@tool
def search_news(question: str) -> str:
    """Search news by meaning and return the source article and companies mentioned."""
    result = retriever.search(query_text=question, top_k=5)
    return json.dumps([item.content for item in result.items])
```

> The embedding model must match the model that built the vector index. A mismatch does not raise an error — it silently returns meaningless results. Re-embed a stored chunk and compare against its saved vector to confirm the pairing.


### 6. Hosted Aura Agents

An [Aura Agent](https://neo4j.com/docs/aura/aura-agent/) is a managed agent configured and hosted in the Aura Console. It reasons over the graph using its own ontology and tools, and returns an answer rather than rows. Exposed over MCP, it becomes a tool in a larger LangChain agent — so graph logic stays with the graph and changes in the Console take effect without a code change.

```python
client = MultiServerMCPClient({
    "aura-agent": {
        "transport": "streamable_http",
        "url": os.environ["AURA_AGENT_MCP_URL"],
        "headers": {"Authorization": f"Bearer {token}"},
    }
})
aura_tools = await client.get_tools()
agent = create_agent(model, aura_tools, system_prompt=prompt)
```

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers like `mcp-neo4j-cypher`, credentials are passed via the `env` parameter at spawn time.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter (e.g., `Authorization: Bearer ${API_TOKEN}`).

❌ **OAuth 2.0 (in-client)** - OAuth2 MCP authentication in-client is not currently supported by the Python SDK.

**Machine-to-machine tokens.** Because in-client OAuth isn't supported, endpoints that expect OAuth can still be used by fetching the token yourself and passing it as a header. For the Aura Agent MCP endpoint, exchange client credentials from the Aura Console (**Account settings → Client credentials → Aura Agent & MCP**) for a bearer token:

```python
token = requests.post(
    "https://mcp.neo4j.io/oauth/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data={
        "grant_type": "client_credentials",
        "client_id": os.environ["AURA_MCP_CLIENT_ID"],
        "client_secret": os.environ["AURA_MCP_CLIENT_SECRET"],
        "audience": "https://agent-mcp.neo4j.io",
    },
).json()["access_token"]
```


**Configuration Example (STDIO transport):**
```python
cypher_mcp_config = {
    "neo4j-database": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-neo4j-cypher"],
        "env": {
            "NEO4J_URI": os.environ.get("NEO4J_URI"),
            "NEO4J_USERNAME": os.environ.get("NEO4J_USERNAME"),
            "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD"),
            "NEO4J_DATABASE": os.environ.get("NEO4J_DATABASE", "neo4j")
        }
    }
}
```

## Resources

- [LangChain Documentation](https://docs.langchain.com/)
- [langchain-neo4j on PyPI](https://pypi.org/project/langchain-neo4j/)
- [langchain-mcp-adapters on GitHub](https://github.com/langchain-ai/langchain-mcp-adapters)
- [neo4j-graphrag for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [Neo4j Aura Agent](https://neo4j.com/docs/aura/aura-agent/)
- [Aura Agent getting started](https://neo4j.com/developer/genai-ecosystem/aura-agent-getting-started/)