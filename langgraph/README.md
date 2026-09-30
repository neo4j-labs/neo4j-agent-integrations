# LangGraph + Neo4j Integration

## Overview

**LangGraph** is a framework for building stateful, multi-actor applications with LLMs. Unlike fixed agent architectures, LangGraph lets you define custom workflows as graphs—giving you full control over how your agent reasons, routes, and executes. It provides cyclical graph structures, built-in persistence, human-in-the-loop patterns, and streaming support.

While it seamlessly integrates with the LangChain ecosystem, it can be used entirely standalone without LangChain as a dependency.

**Installation:**
```bash
pip install langgraph langchain-neo4j langchain-mcp-adapters
```

For the GraphRAG retrieval examples:
```bash
pip install langgraph neo4j-graphrag neo4j
```

**Key Features:**
- Customizable architecture: Define exactly how your agent flows—add validation steps, parallel branches, approval gates, or multi-agent coordination
- Explicit node and edge definitions for agent logic
- Built-in persistence and human-in-the-loop patterns
- Streaming support for real-time responses
- Works standalone or with LangChain integrations
- GraphRAG retrievers from `neo4j-graphrag` wired as routed graph nodes
- Hosted Neo4j Aura Agents callable over MCP as a sub-agent

## Examples

| Notebook | Description |
|----------|-------------|
| [langgraph.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/langgraph/langgraph.ipynb) | Build a company research agent using LangGraph with Neo4j, featuring MCP integration, custom tools, vector search, and graph-based workflow orchestration |
| [langgraph_graphrag.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/langgraph/langgraph_graphrag.ipynb) | Build a routed retrieval graph with `neo4j-graphrag`: a classification node picks between vector, hybrid, and graph-traversal retrievers, and a grading node decides whether to answer or retry |
| [langgraph_aura_agent.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/langgraph/langgraph_aura_agent.ipynb) | Connect a hosted Neo4j Aura Agent to LangGraph as a sub-agent over MCP: machine-to-machine authentication, token caching, and combining the hosted agent with local tools |

## Extension Points

### 1. Custom Graph Architectures

LangGraph's core value is architectural flexibility. You define nodes (functions) and edges (transitions) to create any workflow:
```python
from langgraph.graph import END, START, StateGraph
from typing_extensions import Annotated, TypedDict

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    llm_calls: int

# Build your custom workflow
agent_builder = StateGraph(MessagesState)

# Add nodes - each is a function that transforms state
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Define the flow with edges
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
agent_builder.add_edge("tool_node", "llm_call")

agent = agent_builder.compile()
```

**Example architectures you can build:**
- ReAct loops with tool calling (shown in notebook)
- Multi-agent systems with handoffs
- Pipelines with validation and retry logic
- Human-in-the-loop approval workflows
- Parallel execution branches that merge results

### 2. MCP Integration

Connect to MCP servers using `langchain-mcp-adapters`:
```python
from langchain_mcp_adapters.client import MultiServerMCPClient

cypher_mcp_config = {
    "neo4j-database": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["mcp-neo4j-cypher"],
        "env": {
            "NEO4J_URI": os.environ["NEO4J_URI"],
            "NEO4J_USERNAME": os.environ["NEO4J_USERNAME"],
            "NEO4J_PASSWORD": os.environ["NEO4J_PASSWORD"],
            "NEO4J_DATABASE": os.environ["NEO4J_DATABASE"]
        }
    }
}

client = MultiServerMCPClient(cypher_mcp_config)
mcp_tools = await client.get_tools()
```

### 3. Direct Neo4j Integrations

The `langchain-neo4j` package provides native integrations:

- **Neo4jGraph:** Direct connection for executing Cypher queries within custom tools
- **Neo4jVector:** Vector store integration for semantic search with custom retrieval queries

### 4. Custom Tools

Define custom Neo4j tools using the `@tool` decorator and combine with MCP tools:
```python
from langchain.tools import tool
from langchain_neo4j import Neo4jGraph

neo4j_graph = Neo4jGraph()

@tool
async def get_investments(company: str) -> str:
    """Returns the investments by a company by name."""
    results = neo4j_graph.query("""
        MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
        WHERE o.name = $company
        RETURN i.id as id, i.name as name, head(labels(i)) as type
    """, {"company": company})
    return json.dumps(results, indent=2)
```

### 5. Neo4j Checkpoint Savers

The `langgraph-checkpoint-neo4j` package provides checkpoint savers for persisting agent state to Neo4j:

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

    agent = agent_builder.compile(checkpointer=checkpointer)
```

### 6. GraphRAG Retrievers as Graph Nodes

The `neo4j-graphrag` package provides retrievers that combine vector search with graph traversal:

- **VectorRetriever:** Semantic search over embedded text
- **VectorCypherRetriever:** Vector search followed by a `retrieval_query` that traverses outward from each match, so retrieved text arrives with its source article, dates, and related entities
- **HybridRetriever / HybridCypherRetriever:** Vector and full-text search merged, recovering exact matches on names and tickers that embeddings miss

Each has a different strength, which makes them a natural fit for conditional routing. Instead of leaving the choice to the model, a classification node picks the retriever and a grading node decides whether the result is good enough to answer from:

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

graph_retriever = HybridCypherRetriever(
    driver=driver,
    vector_index_name="news",
    fulltext_index_name="news_fulltext",
    retrieval_query=RETRIEVAL_QUERY,
    embedder=OpenAIEmbeddings(),
)

def graph_search(state: RetrievalState):
    results = graph_retriever.search(query_text=state["question"], top_k=8)
    return {"documents": [item.content for item in results.items]}

builder.add_conditional_edges(
    "route_question", pick_retriever,
    ["vector_search", "hybrid_search", "graph_search"],
)

# Every retriever feeds the same grading node, which cannot be skipped.
for node in ["vector_search", "hybrid_search", "graph_search"]:
    builder.add_edge(node, "grade_context")

builder.add_conditional_edges("grade_context", decide_next, ["graph_search", "generate"])
```

> The embedding model must match the model that built the vector index. A mismatch does not raise an error — it silently returns meaningless results. Re-embed a stored chunk and compare against its saved vector to confirm the pairing.

> `Neo4jVector` from `langchain-neo4j` covers similar ground and returns `Document` objects that slot into existing chains. `neo4j-graphrag` is Neo4j's own library and framework-agnostic, with a wider retriever set and configuration that carries across frameworks unchanged.

### 7. Hosted Aura Agents as Sub-Agents

An [Aura Agent](https://neo4j.com/docs/aura/aura-agent/) is a managed agent configured and hosted in the Aura Console. It reasons over the graph using its own ontology and tools, and returns an answer rather than rows. Exposed over MCP, it becomes a tool your graph can invoke — so one node delegates to an entire agent while the rest of the graph keeps control of the surrounding flow.

```python
client = MultiServerMCPClient({
    "aura-agent": {
        "transport": "streamable_http",
        "url": os.environ["AURA_AGENT_MCP_URL"],
        "headers": {"Authorization": f"Bearer {token}"},
    }
})
aura_tools = await client.get_tools()

# The hosted agent is one tool among your local ones.
all_tools = aura_tools + [portfolio_weight]
tools_by_name = {t.name: t for t in all_tools}
model_with_tools = model.bind_tools(all_tools)

async def tool_node(state: MessagesState):
    """Run the requested tools. One of them is an entire agent hosted in Aura."""
    results = []
    for call in state["messages"][-1].tool_calls:
        observation = await tools_by_name[call["name"]].ainvoke(call["args"])
        results.append(ToolMessage(content=str(observation), tool_call_id=call["id"]))
    return {"messages": results}
```

> Graph logic stays with the graph: the system prompt needs no schema and no Cypher, and updating the agent's ontology in the Console changes behaviour without a code change. LangGraph keeps control of the surrounding flow, which is where you would add validation, approval gates, or additional sub-agents.

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers like `mcp-neo4j-cypher`, credentials are passed via the `env` parameter at spawn time.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter.

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

> These are not Aura API keys — those authenticate against `api.neo4j.io` and belong to the agent's REST endpoint. The token endpoint allows 15 requests per hour per client ID, so cache each token for its full lifetime. MCP tools capture their headers when the client is created, so rebuild the client after the token expires.

**HTTP Transport Configuration (e.g., for Google Colab):**
```python
cypher_mcp_config = {
    "neo4j-database": {
        "url": "http://localhost:8000/mcp",
        "transport": "streamable_http"
    }
}
```

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph on GitHub](https://github.com/langchain-ai/langgraph)
- [langchain-neo4j on PyPI](https://pypi.org/project/langchain-neo4j/)
- [langchain-mcp-adapters on GitHub](https://github.com/langchain-ai/langchain-mcp-adapters)
- [neo4j-graphrag for Python](https://neo4j.com/docs/neo4j-graphrag-python/current/)
- [Neo4j Aura Agent](https://neo4j.com/docs/aura/aura-agent/)
- [Aura Agent getting started](https://neo4j.com/developer/genai-ecosystem/aura-agent-getting-started/)
