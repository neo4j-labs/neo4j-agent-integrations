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

## Samples

This directory contains three end-to-end samples, each demonstrating a different integration pattern between Databricks
and Neo4j via custom and official [Neo4j MCP server](https://github.com/neo4j/mcp).
Samples can be deployed using Databricks SDK/CLI or via Databricks UI and use the public Neo4j companies demo database: `neo4j+s://demo.neo4jlabs.com:7687` by default.

| # | Sample | Pattern | Auth Model | Deployment |
|---|--------|---------|------------|------------|
| 1 | [UC Functions MCP Tools](samples/1-uc-functions/) | UC Functions as Tools | In code, protected by UC Governance | Databricks Notebook |
| 2 | [Custom MCP Server — Using Databricks App](samples/2-custom-mcp-server/) | Python Custom MCP Server as Databricks App | Databricks Secrets | Databricks CLI |
| 3 | [Official MCP Server — Using Databricks App](samples/3-official-mcp-server/) | Official MCP Server as Databricks App | Databricks Secrets | Databricks CLI |

### Sample 1: UC Functions MCP Tools

Uses custom UC Functions Tools that perform requests on Neo4j.
Neo4j credentials are kept in the function, not intended for production but for fast-prototyping.

→ **[Full documentation](samples/1-uc-functions/README.md)**

### Sample 2: Custom MCP Server — Using Databricks App

Uses Databricks App to deploy a Custom MCP Server written in Python who defines Neo4j driver queries as Tools.
Neo4j Basic Auth credentials retrieved from Databricks Secrets.

→ **[Full documentation](samples/2-custom-mcp-server/README.md)**

### Sample 3: Official MCP Server — Using Databricks App

Uses Databricks App to deploy the Neo4j Official MCP Server.
Neo4j Basic Auth credentials retrieved from Databricks Secrets.

→ **[A quick guide](samples/3-official-mcp-server/README.md)** walks through the deployment the MCP server in minutes using automated scripts.
→ **[Step-by-step documentation](samples/3-official-mcp-server/STEP_BY_STEP.md)** covers in details all the aspects of the Databricks App implementation.

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

### 3. Direct Integration in Notebooks

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

## Additional Integration Opportunities

- Neo4j as episodic memory backend
- Unity Catalog governance for graph queries
- MLflow tracking for agent performance
- Auto-evaluation of graph query accuracy

## Additional Resources

- **Databricks MCP**: https://docs.databricks.com/en/generative-ai/mcp/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)