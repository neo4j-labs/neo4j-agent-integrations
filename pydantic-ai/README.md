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

## Examples

| Notebook | Description |
|----------|-------------|
| [pydantic_ai.ipynb](./pydantic_ai.ipynb) | Walkthrough of Pydantic AI with Neo4j integration, including MCP server setup, custom tool creation, and query execution |

## Extension Points

### 1. MCP Integration

Pydantic AI has **native MCP support**. MCP servers are passed directly via the `toolsets` parameter to the agent.

- **Neo4j MCP Server:** Leverage the official [Neo4j MCP Server](https://github.com/neo4j/mcp) for ready-made integration

### 2. Direct Neo4j Integration

For more control beyond the MCP server, use the Neo4j Python driver directly:

- **Driver:** `neo4j` driver for executing Cypher within custom tools

### 3. Custom Tools/Functions

Define custom Neo4j tools by passing async Python functions to the agent:

- Schema inference from type hints and docstrings
- Implement functions that execute Cypher queries
- Pass tools via the `tools` parameter alongside MCP toolsets

## MCP Authentication

**Supported Mechanisms:**

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass credentials via the `headers` parameter using Basic or Bearer authentication.

✅ **Environment Variables (STDIO transport)** - For local MCP servers, credentials can be passed via environment variables at spawn time.

✅ **OAuth 2.0 (via FastMCPToolset)** - Available through the FastMCP-based client.

**Configuration Example (HTTP transport):**
```python
credentials = base64.b64encode(
    f"{os.environ['NEO4J_USERNAME']}:{os.environ['NEO4J_PASSWORD']}".encode()
).decode()

mcp_server = MCPServerStreamableHTTP(
    'http://localhost:80/mcp',
    headers={'Authorization': f'Basic {credentials}'},
)
```

## Resources

- [Pydantic AI Documentation](https://ai.pydantic.dev/)
- [PyPI](https://pypi.org/project/pydantic-ai/)