# LlamaIndex + Neo4j Integration

## Overview

**LlamaIndex** is an open source data orchestration framework for building LLM-powered applications. It provides data connectors for ingesting from diverse sources, powerful indexing and retrieval mechanisms, query engines and chat interfaces, event-driven workflows for complex agentic applications, and seamless integrations with vector stores, databases, and other LLM frameworks.

**Installation:**

```bash
pip install llama-index-core llama-index-tools-mcp llama-index-vector-stores-neo4jvector
```

**Key Features:**

- Event-driven Workflows and FunctionAgent for building multi-agent applications
- Native Neo4j integrations via `llama-index-vector-stores-neo4jvector` package
- MCP server support through `llama-index-tools-mcp`
- Custom tool creation with `FunctionTool.from_defaults()`
- Support for virtually every major LLM provider (OpenAI, Anthropic, Google, Cohere, Mistral, AWS Bedrock, Azure, and more)
- LlamaCloud tools for document parsing (LlamaParse), classification (LlamaClassify), and extraction (LlamaExtract)

## Examples

| Notebook | Description |
|----------|-------------|
| [llamaindex_functionagent.ipynb](./llamaindex_functionagent.ipynb) | Building a company research agent using LlamaIndex with Neo4j MCP server, custom tools, vector search, and FunctionAgent workflow |
| [build_knowledge_graph_with_neo4j_llamacloud.ipynb](./build_knowledge_graph_with_neo4j_llamacloud.ipynb) | End-to-end pipeline for legal document processing using LlamaClassify, LlamaExtract, and Neo4j knowledge graph construction |

## Extension Points

### 1. MCP Integration

LlamaIndex supports MCP servers via the `llama-index-tools-mcp` package. Use `BasicMCPClient` and `McpToolSpec` to connect to MCP servers and retrieve tools.

- **Neo4j MCP Server:** Leverage the official Neo4j MCP server for schema reading and Cypher query execution

### 2. Direct Neo4j Integrations

LlamaIndex provides native Neo4j integrations:

- **Neo4jVectorStore:** Vector store integration via `llama-index-vector-stores-neo4jvector` for semantic search over graph data with support for hybrid search, metadata filtering, and custom retrieval queries
- **Neo4j Python Driver:** You can always use the Neo4j Python driver directly for executing Cypher queries within custom tools

### 3. Custom Tools/Functions

Define custom Neo4j tools using `FunctionTool.from_defaults()`:

- Implement functions that execute Cypher queries via the Neo4j Python driver
- Wrap Neo4j vector stores as tools with `QueryEngineTool`
- Combine MCP tools with custom tools in a single `FunctionAgent`

### 4. LlamaCloud Tools

Build knowledge graphs from documents using LlamaCloud services:

- **LlamaParse:** Parse complex document formats (PDFs, presentations, etc.)
- **LlamaClassify:** AI-powered document classification with custom rules
- **LlamaExtract:** Extract structured data using Pydantic schemas

## MCP Authentication

**Supported Mechanisms:**

✅ **Environment Variables (STDIO transport)** - For local MCP servers, set environment variables before spawning the process. The `BasicMCPClient` can connect to local processes via stdio transport.

✅ **HTTP Headers (HTTP/SSE transport)** - For remote MCP servers, pass API keys or bearer tokens via the `headers` parameter (e.g., `Authorization: Basic ${CREDENTIALS}` or `Authorization: Bearer ${API_TOKEN}`).

✅ **OAuth 2.0 (in-client)** - The `BasicMCPClient` supports OAuth 2.0 authentication via the `with_oauth()` method with configurable token storage.

**Configuration Example (HTTP transport):**

```python
import os
import base64
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

# Set environment variables for the MCP server
os.environ["NEO4J_URI"] = "neo4j+s://demo.neo4jlabs.com"
os.environ["NEO4J_DATABASE"] = "companies"
os.environ["NEO4J_MCP_TRANSPORT"] = "http"

# Credentials passed via HTTP headers
credentials = base64.b64encode(
    f"{os.environ['NEO4J_USERNAME']}:{os.environ['NEO4J_PASSWORD']}".encode()
).decode()

mcp_client = BasicMCPClient(
    "http://localhost:80/mcp",
    headers={"Authorization": f"Basic {credentials}"},
)

mcp_tool_spec = McpToolSpec(client=mcp_client)
tools = await mcp_tool_spec.to_tool_list_async()
```

## Resources

- [LlamaIndex Documentation](https://docs.llamaindex.ai/)
- [llama-index-tools-mcp on PyPI](https://pypi.org/project/llama-index-tools-mcp/)
- [llama-index-vector-stores-neo4jvector on PyPI](https://pypi.org/project/llama-index-vector-stores-neo4jvector/)
- [LlamaCloud Documentation](https://docs.cloud.llamaindex.ai/)