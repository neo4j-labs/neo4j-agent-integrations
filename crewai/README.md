# CrewAI + Neo4j Integration

## Overview

**CrewAI** provides multi-agent orchestration with specialized roles, task delegation, and production-grade deployment capabilities.

**Official Resources:**
- Website: https://www.crewai.com
- Documentation: https://docs.crewai.com/

## Extension Points

### Direct Integration (Bespoke Tools)

```python
from crewai import Agent, Task, Crew
from crewai_tools import tool
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

@tool("Query company from Neo4j")
def query_company(company_name: str) -> dict:
    """Query company information."""
    query = """
        MATCH (o:Organization {name: $company})
        RETURN o.name as name,
               [(o)-[:LOCATED_IN]->(loc:Location) | loc.name] as locations
        LIMIT 1
    """
    records, summary, keys = driver.execute_query(
        query,
        company=company_name,
        database_="companies"
    )
    return records[0].data() if records else {}

# Create specialized agents
researcher = Agent(
    role="Database Researcher",
    goal="Query Neo4j for company information",
    backstory="Expert at querying graph databases",
    tools=[query_company],
    verbose=True
)

analyst = Agent(
    role="Investment Analyst",
    goal="Analyze company data and generate reports",
    backstory="Expert investment analyst",
    verbose=True
)

# Define tasks
research_task = Task(
    description="Research {company} using Neo4j",
    agent=researcher,
    expected_output="Company data from Neo4j"
)

analysis_task = Task(
    description="Analyze the research and create investment report",
    agent=analyst,
    expected_output="Investment research report"
)

# Create crew
crew = Crew(
    agents=[researcher, analyst],
    tasks=[research_task, analysis_task],
    verbose=True
)

# Execute
result = crew.kickoff(inputs={"company": "Google"})
```

## MCP Authentication

⚠️ **Bespoke tools** - No native MCP support

## Resources

- **CrewAI Docs**: https://docs.crewai.com/
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ⚠️ Bespoke integration
- ✅ Multi-agent orchestration
- **Effort Score**: 5/10
- **Impact Score**: 4/10
