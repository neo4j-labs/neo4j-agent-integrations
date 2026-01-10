# IBM watsonx Orchestrate + Neo4j Integration

## Overview

**IBM watsonx Orchestrate** is framework-agnostic (LangChain, LangGraph, CrewAI, BeeAI) with IBM Agent Connect for partner agents, native Graph RAG, and MCP support (May 2025 launch).

**Official Resources:**
- Website: https://www.ibm.com/watsonx
- Documentation: https://www.ibm.com/docs/en/watsonx-as-a-service

## Extension Points

### 1. MCP Support (May 2025)

```python
from ibm_watsonx import Agent, MCPClient

mcp_client = MCPClient(
    url="http://localhost:8000/mcp",
    auth={"type": "ibm_cloud_iam", "api_key": "your-api-key"}
)

agent = Agent(
    name="research_agent",
    mcp_servers=[mcp_client]
)
```

### 2. Framework-Agnostic Integration

Use with LangChain, LangGraph, or CrewAI (see respective guides).

### 3. Native Graph RAG

```python
from ibm_watsonx import GraphRAG

graph_rag = GraphRAG(
    neo4j_url="neo4j+s://demo.neo4jlabs.com:7687",
    neo4j_auth=("companies", "companies")
)
```

## MCP Authentication

✅ **API Keys** - IBM Cloud API keys

✅ **OAuth 2.0** - Client credentials

✅ **IBM Cloud IAM** - Role-based access

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#12-ibm-watsonx-orchestrate)

## Resources

- **watsonx**: https://www.ibm.com/watsonx
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ MCP support (May 2025 launch)
- ✅ Framework-agnostic
- ✅ Native Graph RAG
- **Effort Score**: 8.1/10
- **Impact Score**: 5.9/10
