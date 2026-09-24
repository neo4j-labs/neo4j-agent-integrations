# Pydantic AI + Neo4j Integration

## Overview

**Pydantic AI** is a Python framework for building production-ready AI agents. Leveraging Pydantic's powerful validation and serialization capabilities, it provides type-safe tool definitions, structured outputs, dependency injection, and seamless integration with multiple LLM providers.

**Installation:**
```bash
pip install pydantic-ai neo4j
```

**Key Features:**
- Type-safe tool definitions with automatic schema generation
- Structured outputs validated by Pydantic models
- Native MCP support
- Dependency injection for clean, testable code
- Human-in-the-loop approval for tool calls that need review

> **Note:** These notebooks target **Pydantic AI v2**, which replaced `MCPServerStreamableHTTP` with the FastMCP-based `MCPToolset`. Code written against v0/v1 will not import.

## Examples

| Notebook | Description |
|----------|-------------|
| [pydantic_ai.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/pydantic-ai/pydantic_ai.ipynb) | Walkthrough of Pydantic AI with Neo4j integration, including MCP server setup, custom tool creation, structured output, human-in-the-loop approval, and agent memory |
| [pydantic_ai_graphrag.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/pydantic-ai/pydantic_ai_graphrag.ipynb) | Retrieval over unstructured text with the `neo4j-graphrag` package — vector, graph-expanded and hybrid retrievers exposed as typed agent tools with cited output |
| [pydantic_ai_aura_agent.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/pydantic-ai/pydantic_ai_aura_agent.ipynb) | Connecting to a hosted Neo4j Aura Agent over its MCP endpoint, combined with local tools and structured output |

## Extension Points

### 1. MCP Integration

Pydantic AI has **native MCP support**. MCP servers are passed directly via the `toolsets` parameter to the agent.

- **Neo4j MCP Server:** Leverage the official [Neo4j MCP Server](https://github.com/neo4j/mcp) for ready-made integration
- **Composable toolsets:** `.filtered()`, `.renamed()`, `.prefixed()` and `.approval_required()` each return a new wrapped toolset, so one server can back several agents with different permissions

### 2. Direct Neo4j Integration

For more control beyond the MCP server, use the Neo4j Python driver directly:

- **Driver:** `neo4j` driver for executing Cypher within custom tools

### 3. Custom Tools/Functions

Define custom Neo4j tools by passing async Python functions to the agent:

- Schema inference from type hints and docstrings
- Implement functions that execute Cypher queries
- Pass tools via the `tools` parameter alongside MCP toolsets
- Group related tools in a `FunctionToolset`, which can carry its own `instructions` and be shared across agents

### 4. GraphRAG Retrieval

For questions answered by text rather than by structure, the [`neo4j-graphrag`](https://neo4j.com/docs/neo4j-graphrag-python/) package provides retrievers that can be wrapped as agent tools:

- **`VectorRetriever`** — semantic search over an embedding index
- **`VectorCypherRetriever`** — every hit expanded through the graph via a `retrieval_query`
- **`HybridRetriever` / `HybridCypherRetriever`** — vector plus full-text, for questions naming a specific entity
- Combine with `output_type` to make citations part of the schema rather than an instruction the model can forget

See [pydantic_ai_graphrag.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/pydantic-ai/pydantic_ai_graphrag.ipynb).

### 5. Hosted Aura Agents

A [Neo4j Aura Agent](https://console.neo4j.io) is configured in the console and hosted by Neo4j behind an MCP endpoint, so schema knowledge and query generation live with the agent rather than in your prompt.

- **Endpoint:** `https://mcp.neo4j.io/agent?project_id=<id>&agent_id=<id>`
- **Auth:** OAuth 2.0 client credentials — machine-to-machine, no browser
- Attaches as an ordinary `MCPToolset`, so it composes with local tools in the same agent

See [pydantic_ai_aura_agent.ipynb](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/pydantic-ai/pydantic_ai_aura_agent.ipynb).

## MCP Authentication

**Supported Mechanisms:**

✅ **HTTP Headers (HTTP transport)** - For remote MCP servers, pass credentials via the `headers` parameter using Basic or Bearer authentication.

✅ **Environment Variables (STDIO transport)** - For local MCP servers, credentials can be passed via environment variables at spawn time.

✅ **OAuth 2.0** - `MCPToolset` is built on FastMCP and accepts an `auth` argument for OAuth flows.

**Configuration Example (HTTP transport):**
```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPToolset

credentials = base64.b64encode(
    f"{os.environ['NEO4J_USERNAME']}:{os.environ['NEO4J_PASSWORD']}".encode()
).decode()

neo4j_mcp = MCPToolset(
    'http://127.0.0.1:8002/mcp',
    headers={'Authorization': f'Basic {credentials}'},
    id='neo4j',
)

agent = Agent('openai:gpt-5.4-mini', toolsets=[neo4j_mcp])
```

## Resources

- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [PyPI](https://pypi.org/project/pydantic-ai/)
- [neo4j-graphrag Documentation](https://neo4j.com/docs/neo4j-graphrag-python/current/)
