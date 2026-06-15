# Neo4j Agent Integrations

Integration guides and working examples for connecting Neo4j to 20+ AI agent platforms and frameworks.

## Overview

This repository provides self-contained integration guides showing how to build agents that use Neo4j as their knowledge layer. Each integration demonstrates the same reference implementation adapted to the platform's patterns.

## Quick Start

1. Choose a platform from [Platform Coverage](#platform-coverage)
2. Navigate to its folder (e.g., `langraph/`, `aws-agentcore/`)
3. Follow the README for setup and examples
4. Use the demo database to test

## Demo Database

All examples use a read-only Neo4j instance with company and news data:

```python
NEO4J_URI = "neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_USERNAME = "companies"
NEO4J_PASSWORD = "companies"
NEO4J_DATABASE = "companies"
```

**Dataset:** 250k entities from Diffbot's knowledge graph
- Organizations, people, locations, industries
- News articles with vector embeddings

**Data model:**
```
(Organization)-[:LOCATED_IN]->(Location)
(Organization)-[:IN_INDUSTRY]->(Industry)
(Person)-[:WORKS_FOR]->(Organization)
(Article)-[:MENTIONS]->(Organization)
(Article)-[:HAS_CHUNK]->(Chunk) [vector embeddings]
```

## Reference Implementation

See **[EXAMPLE_AGENT.md](./EXAMPLE_AGENT.md)** for the canonical "Industry Research Agent" that each platform implements.

The reference agent demonstrates:
- Querying company data from Neo4j
- Vector search over news articles
- Analyzing organizational relationships
- Synthesizing research reports

This provides a consistent pattern for comparing integration approaches across platforms.

## Platform Coverage

### Cloud Providers
- **[aws-agentcore](./aws-agentcore/)** - AWS AgentCore Bedrock (native MCP + A2A)
- **[microsoft-foundry](./microsoft-foundry/)** - Azure AI Foundry (native MCP + A2A)
- **[google-gemini-enterprise](./google-gemini-enterprise/)** - Google Gemini Enterprise (MCP + Vertex AI Extensions)

### Vertical Platforms
- **[databricks-agent-bricks](./databricks-agent-bricks/)** - Databricks (MCP Catalog + Unity Catalog)
- **[snowflake-cortex](./snowflake-cortex/)** - Snowflake Cortex
- **[servicenow-ai-agents](./servicenow-ai-agents/)** - ServiceNow (MCP + A2A)
- **[salesforce-agentforce](./salesforce-agentforce/)** - Salesforce Agentforce

### Agent Frameworks
- **[langgraph](./langgraph/)** - LangGraph (MCP adapters)
- **[langchain](./langchain/)** - LangChain (MCP adapters)
- **[microsoft-agent-framework](./microsoft-agent-framework/)** - Microsoft Agent Framework (AutoGen + Semantic Kernel)
- **[openai-agents-sdk](./openai-agents-sdk/)** - OpenAI Agents SDK
- **[strands-agents](./aws-strands-agents/)** - AWS Strands
- **[google-adk](./google-adk/)** - Google ADK
- **[crewai](./crewai/)** - CrewAI
- **[pydantic-ai](./pydantic-ai/)** - Pydantic AI
- **[llamaindex](./llamaindex/)** - LlamaIndex
- **[haystack](./haystack/)** - Haystack
- **[claude-agent](./claude-agent/)** - Claude Agent

### Workflow & Orchestration
- **[ibm-watsonx](./ibm-watsonx/)** - IBM watsonx Orchestrate
- **[n8n](./n8n/)** - n8n
- **[langflow](./langflow/)** - Langflow

## Integration Patterns

### 1. MCP Integration

Use the [Neo4j MCP server](https://github.com/neo4j/mcp) for standardized tool interface:

```python
from mcp_client import MCPClient

client = MCPClient(url="http://localhost:8000/mcp")
tools = client.list_tools()  # Neo4j query tools available
```

The MCP server can run:
- Locally via stdio
- As HTTP service (SSE or streamable-http)
- Deployed to cloud (Cloud Run, Lambda, etc.)

### 2. Direct Integration for Tools

Use Neo4j driver directly for more control:

```python
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

def query_company(company_name: str):
    query = """
    MATCH (o:Organization {name: $company})
    RETURN o.name as name,
           [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
           [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries
    LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        database_="companies"
    )
    return records[0].data() if records else {}
```

### 3. Custom Integrations

Use dedicated extension points of the agent framework to implement a specific integration.



## Authentication

Different platforms support different auth mechanisms. See **[mcp-auth-support.md](./mcp-auth-support.md)** for detailed comparison.

**Common patterns:**
- **API Keys** - Simplest, supported everywhere
- **OAuth M2M** - Enterprise platforms (AWS, Azure, Databricks, ServiceNow)
- **Platform IAM** - Cloud-native (AWS IAM, Azure AD, GCP Service Accounts)

## Repository Structure

```
platform-name/
├── README.md              # Integration guide with working examples
├── examples/              # Complete code samples (optional)
└── challenges.md          # Known issues and workarounds (optional)
```

Each platform README includes:
1. Platform overview and official links
2. Extension points (how to integrate)
3. Authentication setup
4. **Complete implementation of the reference agent**
5. Challenges and limitations
6. Additional integration opportunities

See **[INTEGRATION_TEMPLATE.md](./INTEGRATION_TEMPLATE.md)** for the template.

## Common Queries

**Get company information:**
```cypher
MATCH (o:Organization {name: $company})
RETURN o.name as name,
       [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations,
       [(o)-[:IN_INDUSTRY]->(ind:Industry) | ind.name] as industries,
       [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
LIMIT 1
```

**Vector search news articles:**
```cypher
MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
MATCH (a)-[:HAS_CHUNK]->(c:Chunk)
CALL db.index.vector.queryNodes('news', 5, $embedding)
YIELD node, score
WHERE node = c
RETURN a.title, a.date, c.text, score
ORDER BY score DESC
```

## Contributing

When adding a new integration:

1. Use [INTEGRATION_TEMPLATE.md](./INTEGRATION_TEMPLATE.md) as starting point
2. Implement the reference agent from [EXAMPLE_AGENT.md](./EXAMPLE_AGENT.md)
3. Include working code examples
4. Document authentication setup clearly
5. Note platform-specific challenges and workarounds
6. Keep examples self-contained (no external dependencies beyond Neo4j MCP server)

## Resources

- **Neo4j MCP Server**: https://github.com/neo4j/mcp
- **MCP Specification**: https://modelcontextprotocol.io/
- **Neo4j Driver Docs**: https://neo4j.com/docs/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)
