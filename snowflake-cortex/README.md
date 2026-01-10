# Snowflake Cortex Agents + Neo4j Integration

## Overview

**Snowflake Cortex Agents** (GA November 2025) provides agent capabilities within Snowflake, optimized for Claude 3.5. It processes both structured data (via Cortex Analyst) and unstructured data (via Cortex Search).

**Key Features:**
- Cortex Search for unstructured data
- Cortex Analyst for structured data (SQL generation)
- Data Science Agent
- Multi-step orchestration
- Governance built-in
- REST API + MCP Server support

**Official Resources:**
- Website: https://www.snowflake.com/en/data-cloud/cortex
- Documentation: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents

## Extension Points

### 1. MCP Server Support

Deploy Neo4j MCP server and connect from Cortex Agents:

```python
from snowflake.cortex import Agent

agent = Agent(
    name="investment_researcher",
    tools=[
        {
            "type": "mcp",
            "url": "https://your-neo4j-mcp-server.com/mcp",
            "auth": {"type": "bearer", "token": "your-token"}
        }
    ]
)
```

### 2. Direct Integration via UDF

```sql
CREATE OR REPLACE FUNCTION query_neo4j(company_name VARCHAR)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.8'
PACKAGES = ('neo4j')
HANDLER = 'query_company'
AS
$$
from neo4j import GraphDatabase

def query_company(company_name):
    driver = GraphDatabase.driver(
        "bolt://demo.neo4jlabs.com:7687",
        auth=("companies", "companies")
    )
    with driver.session(database="companies") as session:
        result = session.run("""
            MATCH (o:Organization {name: $name})
            RETURN o.name as name
        """, name=company_name)
        return result.single().data()
$$;
```

### 3. External Functions

Call Neo4j via Snowflake external function (AWS Lambda, Azure Functions).

## MCP Authentication

✅ **API Keys** - Snowflake API keys

✅ **OAuth** - Client credentials flow

✅ **OAuth 2.0** - M2M flows

**Other:**
- Snowflake native authentication
- Unity Catalog-style governance

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#11-snowflake-cortex-agents)

## Industry Research Agent Example

```python
from snowflake.cortex import Agent, Tool
from neo4j import GraphDatabase

# Define Neo4j tools
class Neo4jTools:
    def __init__(self):
        self.driver = GraphDatabase.driver(
            "bolt://demo.neo4jlabs.com:7687",
            auth=("companies", "companies")
        )
    
    @Tool(description="Query company information")
    def query_company(self, name: str) -> dict:
        with self.driver.session(database="companies") as session:
            result = session.run("""
                MATCH (o:Organization {name: $name})
                OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc)
                RETURN o.name, collect(loc.name) as locations
            """, name=name)
            return result.single().data()

# Create agent
agent = Agent(
    name="research_agent",
    model="claude-3-5-sonnet",
    tools=[Neo4jTools().query_company],
    instructions="Research companies using Neo4j data"
)

# Execute
result = agent.run("Research Google")
```

## Challenges and Gaps

1. **MCP support is recent (GA Nov 2025)**
2. **Python UDF limitations** - package versions, execution environment
3. **External function overhead** - network latency

## Additional Integration Opportunities

- Combine Snowflake data warehouse with Neo4j graph
- Use Cortex Search with Neo4j vector embeddings
- Hybrid queries across Snowflake and Neo4j

## Resources

- **Snowflake Cortex Agents**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents
- **Cortex Agents Tutorials**: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-tutorials
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ MCP Server support (GA Nov 2025)
- ✅ Claude 3.5 optimized
- ✅ OAuth 2.0
- **Effort Score**: 6/10
- **Impact Score**: 7/10
