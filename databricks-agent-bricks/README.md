# Databricks Agent Bricks + Neo4j Integration

## Overview

**Databricks Agent Bricks** (Mosaic AI Agent Framework) launched June 2025 with auto-optimization, evaluations, and governance. It features an MCP Catalog, Unity Catalog integration, and support for multiple models (GPT-5, Gemini, Claude, Llama).

**Key Features:**
- MCP Catalog for managed MCP servers
- Unity Catalog integration for governance
- Auto-generates evaluations and tunes agents
- Multi-model support
- Document Intelligence
- MLflow for observability

**Official Resources:**
- Documentation: https://docs.databricks.com/aws/en/generative-ai/agent-framework/create-agent
- MCP Guide: https://docs.databricks.com/en/generative-ai/mcp/
- Authentication: https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent

## Extension Points

### 1. MCP Catalog (Primary)

Install Neo4j MCP server from Databricks Marketplace or manually:

```python
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient

workspace_client = WorkspaceClient(profile="DEFAULT")
host = workspace_client.config.host

client = DatabricksMCPClient(
    servers=[
        f"{host}/api/2.0/mcp/neo4j/prod/company_research"
    ],
    workspace_client=workspace_client
)

# Use tools
tools = client.as_tools()
```

### 2. Unity Catalog Connection

Create Unity Catalog connection for Neo4j:

```sql
CREATE CONNECTION neo4j_prod
  TYPE http
  URL 'https://your-neo4j-mcp-server.com/mcp'
  WITH (
    CREDENTIAL bearer_token SECRET 'your-token'
  );
```

### 3. Direct Integration

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)
```

## MCP Authentication

✅ **Personal Access Tokens (PAT)** - For user access

✅ **Service Principals** (Primary for M2M)
- OAuth M2M required for Agent Bricks Multi-Agent Supervisor
- OAuth application registration in Databricks account

✅ **M2M OIDC**
- OAuth 2.0 with Databricks as Identity Provider
- Dynamic Client Registration support
- Azure AD integration for Azure Databricks

**Other Mechanisms:**
- Unity Catalog permissions
- Managed MCP Proxies (token refresh handled by Databricks)
- On-Behalf-Of-User (OBO) authentication
- Automatic authentication passthrough

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#9-databricks-agent-bricks--mosaic-ai)

## Industry Research Agent Example

```python
import mlflow
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient

# Setup
workspace_client = WorkspaceClient()
mcp_client = DatabricksMCPClient(
    servers=["https://your-workspace/api/2.0/mcp/neo4j/prod"],
    workspace_client=workspace_client
)

# Define agent
class ResearchAgent:
    def __init__(self, tools):
        self.tools = tools
    
    def research_company(self, company_name: str) -> str:
        # Query company data
        company_data = self.tools["query_company"](company_name)
        # Search news
        news = self.tools["search_news"](company_name)
        # Generate report
        return self.synthesize_report(company_data, news)

# Log agent to MLflow
tools = mcp_client.as_tools()
agent = ResearchAgent(tools)

with mlflow.start_run():
    mlflow.log_param("model", "claude-3-5-sonnet")
    mlflow.pyfunc.log_model("research_agent", python_model=agent)

# Deploy
deployment = mlflow.deployments.create_deployment(
    name="research-agent",
    model_uri=f"runs:/{run.info.run_id}/research_agent",
    endpoint="agents"
)
```

## Challenges and Gaps

1. **Custom MCP servers on Databricks Apps don't support PAT**
2. **Unity Catalog connection setup required**
3. **OAuth M2M required for multi-agent systems**

## Additional Integration Opportunities

- Neo4j as episodic memory backend
- Unity Catalog governance for graph queries
- MLflow tracking for agent performance
- Auto-evaluation of graph query accuracy

## Resources

- **Databricks MCP**: https://docs.databricks.com/en/generative-ai/mcp/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ MCP Catalog support
- ✅ Unity Catalog integration
- ✅ OAuth M2M for production
- **Effort Score**: 8.1/10
- **Impact Score**: 8.8/10
