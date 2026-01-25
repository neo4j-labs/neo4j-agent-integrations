# LangGraph + Neo4j Integration

## Overview

**LangGraph** is a framework for building stateful, multi-actor applications with LLMs. Unlike fixed agent architectures, LangGraph lets you define custom workflows as graphs—giving you full control over how your agent reasons, routes, and executes. It provides cyclical graph structures, built-in persistence, human-in-the-loop patterns, and streaming support.

While it seamlessly integrates with the LangChain ecosystem, it can be used entirely standalone without LangChain as a dependency.

**Installation:**
```bash
pip install langgraph langchain-neo4j langchain-mcp-adapters
```

**Key Features:**
- Customizable architecture: Define exactly how your agent flows—add validation steps, parallel branches, approval gates, or multi-agent coordination
- Explicit node and edge definitions for agent logic
- Built-in persistence and human-in-the-loop patterns
- Streaming support for real-time responses
- Works standalone or with LangChain integrations

## Examples

| Notebook | Description |
|----------|-------------|
| [langgraph.ipynb](./langgraph.ipynb) | Build a company research agent using LangGraph with Neo4j, featuring MCP integration, custom tools, vector search, and graph-based workflow orchestration |

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

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers like `mcp-neo4j-cypher`, credentials are passed via the `env` parameter at spawn time.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter.

❌ **OAuth 2.0 (in-client)** - OAuth2 MCP authentication in-client is not currently supported by the Python SDK.

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