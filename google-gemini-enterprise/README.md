# Google Gemini Enterprise (AgentSpace) + Neo4j Integration

## Overview

**Google Gemini Enterprise** (formerly Duet AI) with **AgentSpace** is Google's enterprise AI platform launched October 2025. It provides agent development capabilities with native integration across Google Workspace, M365, Salesforce, and SAP.

**Key Features:**
- AgentSpace for agent development
- Agent Designer (no-code)
- Memory and observability
- Pre-built agents
- MCP + Vertex AI Extensions
- $30/user/month enterprise pricing

**Official Resources:**
- Website: https://cloud.google.com/gemini/enterprise
- Documentation: https://docs.cloud.google.com/gemini/enterprise/docs
- Vertex AI Extensions: https://cloud.google.com/vertex-ai/generative-ai/docs/extensions/overview

## Extension Points

### 1. Vertex AI Extensions

Wrap Neo4j MCP server as a Vertex AI Extension:

```python
from google.cloud import aiplatform

# Create extension
extension = aiplatform.Extension.create(
    display_name="neo4j-research",
    manifest={
        "name": "neo4j_company_research",
        "description": "Query company data from Neo4j",
        "api_spec": {
            "open_api_gcs_uri": "gs://your-bucket/openapi.yaml"
        },
        "auth_config": {
            "auth_type": "GOOGLE_SERVICE_ACCOUNT_AUTH",
            "google_service_account_config": {
                "service_account": "your-service-account@project.iam.gserviceaccount.com"
            }
        }
    }
)
```

### 2. MCP Server via Cloud Run

Deploy Neo4j MCP server on Cloud Run:

```bash
# Deploy MCP server
gcloud run deploy neo4j-mcp \
  --image gcr.io/your-project/neo4j-mcp \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

### 3. Agent Designer

Build agents visually in AgentSpace using Neo4j extension.

## MCP Authentication

✅ **API Keys** - Google Cloud API keys

✅ **Service Accounts** (Primary)
- GCP service account JSON credentials
- OAuth 2.0 service account flows

✅ **Workload Identity Federation**
- For GKE/Cloud Run workloads
- OAuth 2.0 token exchange

**Other Mechanisms:**
- GCP IAM role-based access
- Application Default Credentials (ADC)
- Cloud Run authentication

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#5-google-gemini-enterprise--agentspace-vertex-ai)

## Industry Research Agent Example

```python
import vertexai
from vertexai.preview import reasoning_engines
from neo4j import GraphDatabase

# Initialize Vertex AI
vertexai.init(project="your-project", location="us-central1")

# Neo4j connection
driver = GraphDatabase.driver(
    "neo4j+s://demo.neo4jlabs.com:7687",
    auth=("companies", "companies")
)

# Define tools
def query_company(company_name: str) -> dict:
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

# Create reasoning engine with tools
agent = reasoning_engines.LangchainAgent(
    model="gemini-2.0-flash-exp",
    tools=[query_company],
    agent_executor_kwargs={"return_intermediate_steps": True}
)

# Deploy to Vertex AI
remote_agent = reasoning_engines.ReasoningEngine.create(
    agent,
    requirements=["neo4j", "langchain-google-vertexai"],
    display_name="investment-research-agent"
)

# Query
response = remote_agent.query(
    input="Research Google's organizational structure and industry focus"
)
```

## Challenges and Gaps

1. **MCP Support via Extensions**
   - Not native MCP protocol
   - Need to wrap MCP server as Vertex AI Extension
   - Additional configuration layer

2. **Service Account Setup**
   - Requires GCP IAM configuration
   - Service account key management

3. **Cost Structure**
   - Enterprise pricing per user
   - Additional Vertex AI usage costs

## Additional Integration Opportunities

- Cloud Run for MCP server hosting
- BigQuery integration with Neo4j
- Google Workspace data enrichment
- Gemini 2.0 long-context capabilities

## Resources

- **Gemini Enterprise**: https://cloud.google.com/gemini/enterprise
- **Vertex AI**: https://cloud.google.com/vertex-ai
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)

## Status

- ✅ Vertex AI Extensions support
- ⚠️ MCP via wrapper/extension (not native)
- ✅ GCP Service Accounts
- **Effort Score**: 5.4/10
- **Impact Score**: 7.1/10
