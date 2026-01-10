# Google ADK (Agent Development Kit) + Neo4j Integration

## Overview

**Google ADK** is Google's Agent Development Kit for Vertex AI with agent lifecycle management, deployment capabilities, and structured workflows.

**Key Features:**
- Agent lifecycle management
- Deployment to Vertex AI
- Interface integrations
- Structured workflows
- Python-based development

**Official Resources:**
- GitHub: https://github.com/google/adk-python
- Documentation: https://google.github.io/adk-docs/
- Examples: https://github.com/google/adk-samples

## Extension Points

### 1. Direct Integration (Bespoke)

```python
from google.adk.agents import Agent
from neo4j import GraphDatabase

driver = GraphDatabase.driver(
    "bolt://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

def query_company(company_name: str) -> dict:
    """Query company information from Neo4j."""
    with driver.session(database="companies") as session:
        result = session.run("""
            MATCH (o:Organization {name: $name})
            OPTIONAL MATCH (o)-[:LOCATED_IN]->(loc)
            RETURN o.name, collect(loc.name) as locations
        """, name=company_name)
        return result.single().data()

agent = Agent(
    name="research_agent",
    model="gemini-2.0-flash-exp",
    tools=[query_company],
    instruction="Research companies using Neo4j data"
)
```

### 2. Vertex AI Deployment

Deploy agent with Neo4j integration to Vertex AI:

```bash
# Configure with Vertex AI
export GOOGLE_GENAI_USE_VERTEXAI="1"
export GOOGLE_CLOUD_PROJECT="your-project"
export GOOGLE_CLOUD_LOCATION="us-central1"

# Run locally
uv run adk web

# Deploy to Vertex AI
adk deploy --project your-project --region us-central1
```

## MCP Authentication

⚠️ **Bespoke integrations** - No native MCP support

Use Vertex AI Extensions to wrap MCP servers (see [google-gemini-enterprise](../google-gemini-enterprise/))

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#5-google-gemini-enterprise--agentspace-vertex-ai)

## Resources

- **ADK GitHub**: https://github.com/google/adk-python
- **ADK Docs**: https://google.github.io/adk-docs/
- **Demo Database**: bolt://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ⚠️ Bespoke integration (no native MCP)
- ✅ GCP service accounts
- ✅ Vertex AI deployment
- **Effort Score**: 4.2/10
- **Impact Score**: 6.4/10
