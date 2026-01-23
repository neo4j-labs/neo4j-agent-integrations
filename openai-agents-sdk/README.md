# OpenAI Agents SDK + Neo4j Integration

## Overview

**OpenAI Agents SDK** is OpenAI's Python toolkit for building AI agents. Built on a lightweight, flexible architecture, it provides native tool integration, seamless handoffs between agents, guardrails for input/output validation, and production essentials like tracing, error handling, and session management.

**Installation:**
```bash
pip install openai-agents
```

**Key Features:**
- Native MCP (Model Context Protocol) server support
- Custom tool creation with the `@function_tool` decorator
- Guardrails for input/output validation
- Built-in tracing and error handling
- LiteLLM integration for other LLM providers

## Examples

| Notebook | Description |
|----------|-------------|
| [openai_agents.ipynb](./openai_agents.ipynb) | Walkthrough of OpenAI Agent SDK with Neo4j integration, including MCP server setup, custom tool creation, and query execution |

## Extension Points

### 1. MCP Integration

The OpenAI Agent SDK has **native MCP support**. MCP servers are added directly to `Agent` via the `mcp_servers` parameter.

- **Neo4j MCP Server:** Leverage the official Neo4j MCP server for ready-made integration with schema reading and Cypher execution

### 2. Direct Neo4j Integration

For more control beyond the MCP server, use the Neo4j Python driver directly:

- **Driver:** `neo4j` async driver for executing Cypher within custom tools

### 3. Custom Tools/Functions

Define custom Neo4j tools using the `@function_tool` decorator:

- Specify tool name and description via function signature and docstring
- Pass tools directly to the `Agent` via the `tools` parameter

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers, credentials are passed via the `env` parameter at spawn time.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter (e.g., `Authorization: Basic ${CREDENTIALS}` or `Authorization: Bearer ${TOKEN}`).

✅ **OAuth/Bearer Token (Hosted MCP)** - For OpenAI connectors via `HostedMCPTool`, use the `authorization` field with access tokens.

**Configuration Example (Streamable HTTP transport):**
```python
credentials = base64.b64encode(f"{username}:{password}".encode()).decode()

async with MCPServerStreamableHttp(
    name="Neo4j server",
    params={
        "url": "http://localhost:80/mcp",
        "headers": {"Authorization": f"Basic {credentials}"},
        "timeout": 10,
    },
) as server:
    agent = Agent(
        name="Assistant",
        instructions="Use the MCP tools to answer the questions.",
        mcp_servers=[server],
    )
```

## Resources

- [OpenAI Agent SDK Documentation](https://openai.github.io/openai-agents-python/)
- [PyPI](https://pypi.org/project/openai-agents/)
- [GitHub](https://github.com/openai/openai-agents-python)