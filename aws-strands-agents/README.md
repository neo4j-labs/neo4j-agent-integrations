# AWS Strands Agents + Neo4j Integration

## Overview

**AWS Strands Agents** is a model-agnostic framework with deep AWS Bedrock integration, first-class tracing via OpenTelemetry, and MCP + LiteLLM support.

**Key Features:**
- Model-agnostic (runs anywhere)
- Deep AWS Bedrock integration (optional)
- OpenTelemetry observability
- MCP + LiteLLM support
- Runs on any cloud or local

**Official Resources:**
- GitHub: https://github.com/strands-agents/sdk-python
- Samples: https://github.com/strands-agents/samples
- AWS Blog: https://aws.amazon.com/blogs/opensource/introducing-strands-agents-an-open-source-ai-agents-sdk/

## Extension Points

### 1. MCP Integration

```python
from strands import Agent, MCPTool

neo4j_tools = MCPTool.from_server(
    url="http://localhost:8000/mcp",
    auth={"type": "bearer", "token": "YOUR_TOKEN"}
)

agent = Agent(
    name="research_agent",
    model="anthropic.claude-3-5-sonnet-v2",
    tools=[neo4j_tools]
)
```

### 2. Direct Integration

```python
from strands import Agent, Tool
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

@Tool(description="Query company from Neo4j")
def query_company(name: str) -> dict:
    query = """
        MATCH (o:Organization {name: $company})
        RETURN o.name as name,
               [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations
        LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=name,
        database_="companies"
    )
    return records[0].data() if records else {}

agent = Agent(
    name="research_agent",
    model="gpt-4",
    tools=[query_company]
)
```

## MCP Authentication

✅ **API Keys** - Via custom headers

✅ **AWS IAM** - For AWS deployments

✅ **LiteLLM** - Multi-provider auth support

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#6-aws-agentcore-bedrock-strands-agents)

## Resources

- **GitHub**: https://github.com/awslabs/strands-agents
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ MCP support
- ✅ Model-agnostic
- ✅ AWS IAM integration
- **Effort Score**: 3.9/10
- **Impact Score**: 7.1/10
