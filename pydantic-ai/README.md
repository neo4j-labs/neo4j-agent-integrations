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
    "neo4j+s://demo.neo4jlabs.com:7687",
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

# Execute with type safety
result = agent.run_sync("Research Google")
company: CompanyData = result.data
```

## MCP Authentication

⚠️ **Bespoke tools** - No native MCP support

## Resources

- **Pydantic AI**: https://ai.pydantic.dev/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ⚠️ Bespoke integration
- ✅ Type safety
- ✅ Multi-provider support
- **Effort Score**: 4.4/10
- **Impact Score**: 5.1/10
