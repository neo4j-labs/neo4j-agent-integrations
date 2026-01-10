# Microsoft Agent Framework + Neo4j Integration

## Overview

**Microsoft Agent Framework** is Microsoft's unified agent development framework that merges AutoGen and Semantic Kernel (2025). It provides enterprise-grade agent development with cross-cloud flexibility, comprehensive observability, and governance capabilities.

**Key Features:**
- Unified framework combining AutoGen's multi-agent orchestration with Semantic Kernel's plugin architecture
- MCP + A2A Protocol support (native)
- Enterprise identity and governance
- Memory management
- Autoscaling for production deployments
- Cross-platform (Python, C#, TypeScript)
- Cross-cloud flexibility (not Azure-only)

**Official Resources:**
- Website: https://azure.microsoft.com/en-us/products/ai-foundry
- Documentation: https://learn.microsoft.com/en-us/azure/ai-foundry/
- GitHub: https://github.com/microsoft/autogen (AutoGen) and https://github.com/microsoft/semantic-kernel (Semantic Kernel)

## Extension Points

### 1. MCP Integration (Native)

The Agent Framework has native MCP support inherited from the foundry platform:

**Setup:**
```python
from microsoft.agentframework import AgentFramework
from microsoft.agentframework.mcp import MCPClient

# Configure MCP client
mcp_client = MCPClient(
    url="http://localhost:8000/mcp",
    auth={
        "type": "oauth",
        "client_id": "your-client-id",
        "client_secret": "your-client-secret"
    }
)

# Register MCP tools with framework
framework = AgentFramework()
framework.register_mcp_server("neo4j", mcp_client)
```

### 2. Semantic Kernel Plugins

Define Neo4j operations as Semantic Kernel plugins:

```python
from semantic_kernel.skill_definition import sk_function

class Neo4jPlugin:
    def __init__(self, driver):
        self.driver = driver

    @sk_function(
        description="Query company information from Neo4j",
        name="QueryCompany"
    )
    def query_company(self, company_name: str) -> str:
        with self.driver.session() as session:
            result = session.run("""
                MATCH (o:Organization {name: $name})
                OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc:Location)
                OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind:Industry)
                RETURN o, collect(loc) as locations, collect(ind) as industries
            """, name=company_name)
            return result.single().data()
```

### 3. AutoGen Agents

Use AutoGen's multi-agent pattern with Neo4j tools:

```python
from autogen import AssistantAgent, UserProxyAgent

database_agent = AssistantAgent(
    name="database_agent",
    system_message="You query Neo4j for company and news data.",
    llm_config={"model": "gpt-4"}
)

# Register Neo4j functions
database_agent.register_function(
    function_map={
        "query_company": query_company,
        "search_news": search_news
    }
)
```

## MCP Authentication

**Supported Mechanisms:**

✅ **API Keys** - Via custom headers or query parameters

✅ **Azure AD Client Credentials** (Primary for enterprise)
- Full OAuth 2.0 client credentials flow
- App registrations with client ID/secret
- Entra ID integration

✅ **M2M OIDC** - Azure AD/Entra ID
- OAuth 2.0 Authorization Code Flow
- Dynamic Client Registration (DCR)
- Manual OAuth configuration

**Other Mechanisms:**
- **Managed Identity** - For Azure resources
- **Service Principals** - For application authentication
- **Multiple Identity Providers** - Cognito, Auth0, Okta, custom
- **Cross-cloud IAM** - Works with AWS IAM, GCP Service Accounts when deployed outside Azure

**Configuration Example:**

```python
# Azure AD OAuth
auth_config = {
    "type": "oauth2",
    "authorization_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
    "token_url": "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
    "client_id": "your-app-id",
    "client_secret": "your-app-secret",
    "scope": ["https://graph.microsoft.com/.default"]
}

mcp_client = MCPClient(
    url="https://your-neo4j-mcp-server.com/mcp",
    auth=auth_config
)
```

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#4-microsoft-foundry-copilot-studio-agent-framework)

## Industry Research Agent Example

### Scenario

Build a multi-agent investment research system using Microsoft Agent Framework combining:
1. Semantic Kernel plugins for Neo4j integration
2. AutoGen multi-agent orchestration
3. Azure AD for authentication
4. Enterprise governance and observability

### Dataset Setup

**Company News Knowledge Graph:**
```python
from neo4j import GraphDatabase
import os

# Store in Azure Key Vault for production
NEO4J_URI = "bolt://demo.neo4jlabs.com:7687"
NEO4J_USERNAME = "companies"
NEO4J_PASSWORD = "companies"
NEO4J_DATABASE = "companies"

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)
```

### Implementation

#### Approach 1: Semantic Kernel Plugins

```python
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.skill_definition import sk_function
from neo4j import GraphDatabase
import json

# Initialize Semantic Kernel
kernel = Kernel()

# Add Azure OpenAI service
kernel.add_chat_service(
    "chat",
    AzureChatCompletion(
        deployment_name="gpt-4",
        endpoint="your-azure-openai-endpoint",
        api_key="your-api-key"
    )
)

# Define Neo4j Plugin
class Neo4jResearchPlugin:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
        )

    @sk_function(
        description="Query detailed company information from Neo4j",
        name="query_company"
    )
    def query_company(self, company_name: str) -> str:
        """Query organization data from Neo4j."""
        with self.driver.session(database=NEO4J_DATABASE) as session:
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
            data = result.single()
            return json.dumps(data.data() if data else {})

    @sk_function(
        description="Search news articles about a company using vector similarity",
        name="search_news"
    )
    def search_news(self, company_name: str, query: str) -> str:
        """Vector search for news articles."""
        with self.driver.session(database=NEO4J_DATABASE) as session:
            # Note: Simplified - actual implementation needs embedding generation
            result = session.run("""
                MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
                RETURN a.title as title, a.date as date
                ORDER BY a.date DESC
                LIMIT 5
            """, company=company_name)
            articles = [r.data() for r in result]
            return json.dumps(articles)

    @sk_function(
        description="Analyze organizational relationships and partnerships",
        name="analyze_relationships"
    )
    def analyze_relationships(self, company_name: str) -> str:
        """Find related organizations through graph traversal."""
        with self.driver.session(database=NEO4J_DATABASE) as session:
            result = session.run("""
                MATCH path = (o1:Organization {name: $name})
                             -[*1..2]-(o2:Organization)
                WHERE o1 <> o2
                RETURN DISTINCT o2.name as organization,
                       length(path) as distance
                ORDER BY distance
                LIMIT 10
            """, name=company_name)
            relationships = [r.data() for r in result]
            return json.dumps(relationships)

# Register plugin
neo4j_plugin = kernel.import_skill(Neo4jResearchPlugin(), "Neo4j")

# Create research function
research_function = kernel.create_semantic_function("""
Research the company {{$company_name}}.

1. First, get company information using {{Neo4j.query_company}}
2. Then, search recent news using {{Neo4j.search_news}}
3. Analyze relationships using {{Neo4j.analyze_relationships}}
4. Synthesize all information into an investment research report

Include: Executive Summary, Company Overview, Recent Developments, Network Analysis, Outlook
""", max_tokens=4000)

# Execute research
result = research_function(company_name="Google")
print(result)
```

#### Approach 2: AutoGen Multi-Agent System

```python
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from neo4j import GraphDatabase
import os

# Configure LLM
config_list = [{
    "model": "gpt-4",
    "api_key": os.getenv("AZURE_OPENAI_API_KEY"),
    "base_url": os.getenv("AZURE_OPENAI_ENDPOINT"),
    "api_type": "azure",
    "api_version": "2024-02-15-preview"
}]

llm_config = {"config_list": config_list, "temperature": 0}

# Initialize Neo4j
driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
)

# Define Neo4j query functions
def query_company(company_name: str) -> dict:
    """Query company information from Neo4j."""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (o:Organization {name: $name})
            OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc:Location)
            OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind:Industry)
            OPTIONAL MATCH (p:Person)-[:WORKS_FOR]->(o)
            RETURN o.name as name,
                   collect(DISTINCT loc.name) as locations,
                   collect(DISTINCT ind.name) as industries,
                   collect({name: p.name, title: p.title})[..5] as leadership
            LIMIT 1
        """, name=company_name)
        record = result.single()
        return record.data() if record else {}

def search_news(company_name: str) -> list:
    """Search news articles about a company."""
    with driver.session(database=NEO4J_DATABASE) as session:
        result = session.run("""
            MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
            RETURN a.title as title, a.date as date
            ORDER BY a.date DESC
            LIMIT 5
        """, company=company_name)
        return [r.data() for r in result]

# Create Database Agent
database_agent = AssistantAgent(
    name="database_agent",
    system_message="""You are a database specialist.
    You query Neo4j for company information and news articles.
    Use the available functions to retrieve data.""",
    llm_config=llm_config
)

# Register functions with database agent
database_agent.register_function(
    function_map={
        "query_company": query_company,
        "search_news": search_news
    }
)

# Create Research Analyst Agent
analyst_agent = AssistantAgent(
    name="research_analyst",
    system_message="""You are an investment research analyst.
    You synthesize company data and news into investment reports.
    Focus on: executive summary, key developments, risks, outlook.""",
    llm_config=llm_config
)

# Create User Proxy
user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=0,
    code_execution_config=False
)

# Create Group Chat
groupchat = GroupChat(
    agents=[user_proxy, database_agent, analyst_agent],
    messages=[],
    max_round=10
)

manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)

# Execute research workflow
user_proxy.initiate_chat(
    manager,
    message="""Research Google:
    1. Database agent: Query company information and recent news
    2. Research analyst: Synthesize into an investment research report
    """
)
```

#### Approach 3: Hybrid with MCP Server

```python
from microsoft.agentframework import AgentFramework
from microsoft.agentframework.mcp import MCPClient
from semantic_kernel import Kernel

# Setup MCP client for Neo4j
mcp_client = MCPClient(
    url="http://localhost:8000/mcp",
    auth={"type": "bearer", "token": "your-token"}
)

# Initialize framework
framework = AgentFramework()
framework.register_mcp_server("neo4j", mcp_client)

# Get MCP tools
neo4j_tools = framework.get_tools("neo4j")

# Create agent with MCP tools
kernel = Kernel()
kernel.import_skill(neo4j_tools, "Neo4j")

# Use in Semantic Kernel workflows
research_function = kernel.create_semantic_function("""
Use {{Neo4j.query_company}} and {{Neo4j.search_news}} to research {{$company}}.
Generate an investment research report.
""")

result = research_function(company="Microsoft")
```

## Challenges and Gaps

### Current Limitations

1. **Framework Consolidation**
   - AutoGen and Semantic Kernel merger is ongoing (2025)
   - Some features may have different APIs across components
   - Documentation is transitioning

2. **Cross-Cloud Complexity**
   - While cross-cloud capable, Azure integration is most mature
   - Non-Azure deployments may require additional configuration
   - Authentication patterns vary by cloud provider

3. **MCP Integration Maturity**
   - Native MCP support is new
   - Some MCP features may not be fully integrated with AutoGen patterns
   - Documentation for MCP + AutoGen + Semantic Kernel is evolving

4. **Memory Management**
   - Built-in memory stores are primarily Azure-based
   - Using Neo4j as custom memory backend requires additional implementation
   - Memory API may differ between AutoGen and Semantic Kernel components

### Workarounds

**For Cross-Framework Compatibility:**
```python
# Wrapper to use Semantic Kernel plugin in AutoGen
class SKPluginWrapper:
    def __init__(self, sk_plugin):
        self.plugin = sk_plugin

    def __call__(self, **kwargs):
        return self.plugin.invoke(**kwargs)

# Register SK plugin with AutoGen agent
autogen_agent.register_function(
    function_map={
        "query_company": SKPluginWrapper(neo4j_plugin.query_company)
    }
)
```

**For Neo4j Memory Backend:**
```python
# Custom memory store using Neo4j
class Neo4jMemoryStore:
    def __init__(self, driver):
        self.driver = driver

    async def save_memory(self, agent_id: str, memory: dict):
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Agent {id: $agent_id})
                CREATE (a)-[:HAS_MEMORY]->(m:Memory {
                    timestamp: datetime(),
                    content: $content
                })
            """, agent_id=agent_id, content=memory)

    async def retrieve_memory(self, agent_id: str, limit: int = 10):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Agent {id: $agent_id})-[:HAS_MEMORY]->(m:Memory)
                RETURN m.content as content, m.timestamp as timestamp
                ORDER BY m.timestamp DESC
                LIMIT $limit
            """, agent_id=agent_id, limit=limit)
            return [r.data() for r in result]
```

## Additional Integration Opportunities

### 1. Enterprise Memory Graph

Use Neo4j as the memory layer for agents:
- Store conversation history as graph structures
- Track entity relationships across conversations
- Enable semantic memory retrieval across agent team
- Implement organizational memory policies

### 2. Agent Governance with Neo4j

Track agent actions and decisions:
```python
def log_agent_action(agent_id: str, action: str, result: dict):
    with driver.session() as session:
        session.run("""
            MERGE (a:Agent {id: $agent_id})
            CREATE (a)-[:PERFORMED]->(action:Action {
                type: $action,
                timestamp: datetime(),
                result: $result
            })
        """, agent_id=agent_id, action=action, result=result)
```

### 3. Multi-Agent Collaboration Graph

Model agent relationships and information flow:
- Track which agents collaborate
- Analyze communication patterns
- Optimize agent orchestration based on graph analysis

### 4. Integration with Azure Services

Combine Neo4j with Azure ecosystem:
- Azure Key Vault for credentials
- Azure Monitor for observability
- Azure Functions for serverless Neo4j queries
- Azure Container Apps for MCP server deployment

## Deployment Guide

### Development Setup

```bash
# Install dependencies
pip install semantic-kernel pyautogen neo4j azure-identity

# Configure environment
export AZURE_OPENAI_ENDPOINT="your-endpoint"
export AZURE_OPENAI_API_KEY="your-key"
export NEO4J_URI="bolt://demo.neo4jlabs.com:7687"
export NEO4J_USER="companies"
export NEO4J_PASSWORD="companies"
```

### Production Deployment

```python
# Using Azure Key Vault
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

credential = DefaultAzureCredential()
client = SecretClient(
    vault_url="https://your-vault.vault.azure.net/",
    credential=credential
)

neo4j_uri = client.get_secret("neo4j-uri").value
neo4j_password = client.get_secret("neo4j-password").value

# Use in agent framework
driver = GraphDatabase.driver(
    neo4j_uri,
    auth=("neo4j", neo4j_password)
)
```

## Resources

- **Agent Framework Docs**: https://learn.microsoft.com/en-us/azure/ai-foundry/
- **AutoGen GitHub**: https://github.com/microsoft/autogen
- **Semantic Kernel GitHub**: https://github.com/microsoft/semantic-kernel
- **Neo4j MCP Server**: https://github.com/neo4j/mcp
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Framework merger announced (2025)
- ✅ Native MCP + A2A support
- ✅ Enterprise identity and governance
- ✅ Cross-cloud flexibility
- ⚠️ Documentation transitioning between AutoGen/SK merger
- ⚠️ MCP integration with AutoGen patterns maturing
- 🔄 Active Microsoft investment

**Effort Score**: 5.9/10
**Impact Score**: 5.9/10

## Notes

The Microsoft Agent Framework represents a strategic consolidation of Microsoft's agent development tools. The merger of AutoGen (multi-agent orchestration) and Semantic Kernel (plugin architecture) creates a powerful unified framework, though documentation and patterns are still evolving. Neo4j integration can leverage both components for maximum flexibility.
