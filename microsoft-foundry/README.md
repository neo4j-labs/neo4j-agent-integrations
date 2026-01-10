# Microsoft Foundry (Azure AI Foundry) + Neo4j Integration

## Overview

**Microsoft Foundry** (formerly Azure AI Foundry, rebranded November 2025) is Microsoft's enterprise AI platform. It's the only cloud platform offering both Claude and GPT models with enterprise-grade governance, native MCP + A2A Protocol support, and comprehensive identity management.

**Key Features:**
- Native MCP + A2A Protocol support
- Both Claude and GPT models available
- Enterprise identity (Azure AD/Entra ID)
- Memory, observability, evaluations
- Policy controls and governance
- Cross-cloud flexibility

**Official Resources:**
- Documentation: https://learn.microsoft.com/en-us/azure/ai-foundry/
- MCP Guide: https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent
- Copilot Studio: https://learn.microsoft.com/en-us/microsoft-copilot-studio/

## Extension Points

### 1. MCP Integration (Native)

Microsoft Foundry has first-class MCP support with three OAuth setup types:

1. **Dynamic Discovery** - Automatic endpoint discovery via DCR
2. **Dynamic without discovery** - Manual endpoint configuration with DCR
3. **Manual** - Full manual OAuth 2.0 setup

**Configuration:**
```json
{
  "mcp_servers": {
    "neo4j": {
      "url": "https://your-neo4j-mcp-server.com/mcp",
      "auth": {
        "type": "oauth2",
        "authorization_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret",
        "scope": "api://your-app-id/.default"
      }
    }
  }
}
```

### 2. Copilot Studio Integration

Build agents in Copilot Studio with Neo4j MCP server as a data source.

### 3. Direct Integration

Use Azure Functions or Azure Container Apps with Neo4j driver for custom tools.

## MCP Authentication

✅ **API Keys** - Supported as header or query parameter

✅ **Azure AD Client Credentials** (Primary)
- Full OAuth 2.0 client credentials flow
- App registrations with client ID/secret

✅ **M2M OIDC** - Azure AD/Entra ID
- Dynamic Client Registration (DCR)
- Manual OAuth configuration
- Multiple identity providers supported

**Other Mechanisms:**
- Managed Identity for Azure resources
- Service Principals
- APIM for additional auth layers
- CORS configuration for cloud deployments

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#4-microsoft-foundry-copilot-studio-agent-framework)

## Industry Research Agent Example

### Implementation

```python
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from neo4j import GraphDatabase
import os

# Azure AI Foundry setup
credential = DefaultAzureCredential()
project_client = AIProjectClient(
    endpoint=os.getenv("AZURE_AI_PROJECT_ENDPOINT"),
    credential=credential
)

# Neo4j setup
driver = GraphDatabase.driver(
    "bolt://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

# Define Neo4j tools
def query_company(company_name: str) -> dict:
    """Query company information from Neo4j."""
    with driver.session(database="companies") as session:
        result = session.run("""
            MATCH (o:Organization {name: $name})
            OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc:Location)
            OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind:Industry)
            OPTIONAL MATCH (p:Person)-[:WORKS_FOR]->(o)
            RETURN o.name as name,
                   collect(DISTINCT loc.name) as locations,
                   collect(DISTINCT ind.name) as industries,
                   collect({name: p.name, title: p.title}) as leadership
            LIMIT 1
        """, name=company_name)
        record = result.single()
        return record.data() if record else {}

def search_news(company_name: str, query: str) -> list:
    """Search news articles about a company."""
    with driver.session(database="companies") as session:
        result = session.run("""
            MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
            RETURN a.title as title, a.date as date
            ORDER BY a.date DESC
            LIMIT 5
        """, company=company_name)
        return [r.data() for r in result]

# Create agent with tools
agent = project_client.agents.create_agent(
    model="gpt-4",
    name="investment_researcher",
    instructions="""You are an investment research analyst.
    Use the available tools to research companies and generate reports.""",
    tools=[
        {"type": "function", "function": query_company},
        {"type": "function", "function": search_news}
    ]
)

# Or use MCP server
mcp_tools = project_client.mcp.get_tools("neo4j")
agent = project_client.agents.create_agent(
    model="claude-3-5-sonnet-20241022",  # Foundry supports both Claude and GPT
    name="investment_researcher",
    tools=mcp_tools
)

# Execute research
thread = project_client.agents.create_thread()
message = project_client.agents.create_message(
    thread_id=thread.id,
    role="user",
    content="Research Google's recent activities and generate a report"
)

run = project_client.agents.create_run(
    thread_id=thread.id,
    agent_id=agent.id
)

# Wait for completion and get results
result = project_client.agents.get_run(thread.id, run.id)
messages = project_client.agents.list_messages(thread.id)
```

## Challenges and Gaps

### Current Limitations

1. **Authentication Complexity**
   - OAuth 2.0 setup requires Azure AD app registration
   - Multiple configuration options can be confusing
   - Token management needs understanding of Azure identity

2. **Cost Structure**
   - Enterprise pricing model
   - Both Azure infrastructure and model costs

3. **Vendor Lock-in Concerns**
   - While cross-cloud capable, Azure-native features are most mature
   - Some features tied to Azure services

### Workarounds

**Simplified Auth for Development:**
```python
# Use Azure CLI credentials for local dev
from azure.identity import AzureCliCredential
credential = AzureCliCredential()
```

## Additional Integration Opportunities

### 1. Azure Services Integration
- Azure Key Vault for secrets
- Azure Monitor for observability
- Azure Container Apps for MCP server hosting
- Azure API Management for governance

### 2. Copilot Studio Low-Code
- Build agents visually
- Neo4j MCP server as connector
- Enterprise governance built-in

### 3. Multi-Model Support
- Use Claude for complex reasoning
- Use GPT for cost-effective queries
- Model routing based on task

## Resources

- **Microsoft Foundry**: https://learn.microsoft.com/en-us/azure/ai-foundry/
- **MCP Guide**: https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent
- **Neo4j MCP Server**: https://github.com/neo4j/mcp
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Native MCP + A2A support
- ✅ Both Claude and GPT models
- ✅ Enterprise OAuth 2.0 with DCR
- ✅ Comprehensive governance
- **Effort Score**: 6.5/10
- **Impact Score**: 7.3/10
