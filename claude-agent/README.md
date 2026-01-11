# Claude Agent SDK + Neo4j Integration

## Overview

**Claude Agent SDK** is Anthropic's Python toolkit for building AI agents. Built on the same agent harness that powers Claude Code, it provides automatic context management, a rich tool ecosystem, fine-grained permissions, and production essentials like error handling and session management.

**Installation:**
```bash
pip install claude-agent-sdk neo4j
```

**Key Features:**
- Automatic context management across conversations
- Native MCP (Model Context Protocol) server support
- Custom tool creation with the `@tool` decorator
- Subagent orchestration for parallel and specialized workflows
- Session persistence and resumption
- Support for multiple LLM providers (Anthropic API, AWS Bedrock, Google Vertex AI, Microsoft Azure)

## Examples

| Notebook | Description |
|----------|-------------|
| [claude_agent_sdk.ipynb](./claude_agent_sdk.ipynb) | Walkthrough of Claude Agent SDK with Neo4j integration, including MCP server setup, custom tool creation, and query execution |

## Extension Points

### 1. MCP Integration

The Claude Agent SDK has **native MCP support**. MCP servers are added directly to `ClaudeAgentOptions` via the `mcp_servers` parameter—no adapters required.

- **Neo4j MCP Server:** Leverage existing MCP servers such as `mcp-neo4j-cypher` for ready-made integration

### 2. Direct Neo4j Integration

For more control beyond the MCP server, use the Neo4j Python driver directly:

- **Driver:** `neo4j` driver for executing Cypher within custom tools

### 3. Custom Tools/Functions

Define custom Neo4j tools using the `@tool` decorator:

- Specify tool name, description, and input schema
- Implement functions that execute Cypher queries
- Return results as structured content blocks
- Bundle tools into an in-process MCP server with `create_sdk_mcp_server()`

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers like `mcp-neo4j-cypher`, credentials are passed via the `env` parameter at spawn time.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter (e.g., `Authorization: Bearer ${API_TOKEN}`).

❌ **OAuth 2.0 (in-client)** - OAuth2 MCP authentication in-client is not currently supported by the SDK.

**Configuration Example (STDIO transport):**
```python
cypher_mcp_config = {
    "type": "stdio",
    "command": "uvx",
    "args": ["mcp-neo4j-cypher"],
    "env": {
        "NEO4J_URI": os.environ.get("NEO4J_URI"),
        "NEO4J_USERNAME": os.environ.get("NEO4J_USERNAME"),
        "NEO4J_PASSWORD": os.environ.get("NEO4J_PASSWORD"),
        "NEO4J_DATABASE": os.environ.get("NEO4J_DATABASE", "neo4j")
    }
}
```
## Resources

- [Claude Agent SDK Documentation](https://platform.claude.com/docs/en/agent-sdk/overview)
- [PyPI](https://pypi.org/project/claude-agent-sdk/)