# LangChain + Neo4j Integration

## Overview

**LangChain** is a Python toolkit for building applications powered by large language models. It provides composable chains and agents, a vast integration ecosystem, memory and retrieval systems, and production essentials like callbacks, tracing, and evaluation tools.

**Installation:**
```bash
pip install langchain langchain-neo4j langchain-mcp-adapters
```

**Key Features:**
- Composable chains and ReAct-style agents
- Native Neo4j integrations via `langchain-neo4j` package
- MCP server support through `langchain-mcp-adapters`
- Custom tool creation with the `@tool` decorator
- Support for virtually every major LLM provider (OpenAI, Anthropic, Google, Cohere, Mistral, AWS Bedrock, Azure, and more)

## Examples

| Notebook | Description |
|----------|-------------|
| [langchain.ipynb](./langchain.ipynb) | Walkthrough of LangChain with Neo4j integration, including MCP server setup, custom tool creation, vector search, and query execution |

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

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers like `mcp-neo4j-cypher`, credentials are passed via the `env` parameter at spawn time.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter (e.g., `Authorization: Bearer ${API_TOKEN}`).

❌ **OAuth 2.0 (in-client)** - OAuth2 MCP authentication in-client is not currently supported by the Python SDK.

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