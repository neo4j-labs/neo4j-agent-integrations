# Pydantic AI + Neo4j Integration

## Overview

**Pydantic AI** is a type-safe agent framework with schema validation, multi-provider support, and built-in monitoring via Logfire.

**Official Resources:**
- Website: https://ai.pydantic.dev
- Documentation: https://ai.pydantic.dev/

## Extension Points

### Direct Integration with Type Safety

```python
from pydantic_ai import Agent, RunContext
from pydantic import BaseModel
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

class CompanyData(BaseModel):
    name: str
    locations: list[str]
    industries: list[str]

agent = Agent(
    'openai:gpt-4',
    result_type=CompanyData,
    system_prompt='Research companies using Neo4j data'
)

@agent.tool
def query_company(ctx: RunContext, company_name: str) -> dict:
    """Query company from Neo4j."""
    with driver.session(database="companies") as session:
        result = session.run("""
            MATCH (o:Organization {name: $name})
            OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc)
            OPTIONAL MATCH (o)-[:IN_INDUSTRY]->(ind)
            RETURN o.name as name,
                   collect(DISTINCT loc.name) as locations,
                   collect(DISTINCT ind.name) as industries
        """, name=company_name)
        return result.single().data()

# Execute with type safety
result = agent.run_sync("Research Google")
company: CompanyData = result.data
```

## MCP Authentication

⚠️ **Bespoke tools** - No native MCP support

## Resources

- **Pydantic AI**: https://ai.pydantic.dev/
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ⚠️ Bespoke integration
- ✅ Type safety
- ✅ Multi-provider support
- **Effort Score**: 4.4/10
- **Impact Score**: 5.1/10
