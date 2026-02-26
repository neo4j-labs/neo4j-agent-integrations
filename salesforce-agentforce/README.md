# Salesforce Agentforce + Neo4j Integration

## Overview

**Salesforce Agentforce** is Salesforce's enterprise AI agent platform powered by the **Atlas Reasoning Engine (ARE)** — a ReAct-style orchestration loop that plans, selects tools, observes results, and iterates to answer user queries.

**Key Features:**
- Atlas Reasoning Engine (plan → act → observe → decide loop)
- Topics (semantic routing layer) + Actions (tool execution layer)
- Native MCP client (Pilot July 2025, Beta features October 2025)
- External Service Actions — import any OpenAPI 3.0 spec as agent tools
- Apex Actions — full Java-like server-side code for complex integrations
- BYOM (Bring Your Own Model) — connect Claude, GPT-4, Gemini via your accounts
- Einstein Trust Layer — PII masking, zero data retention with LLM providers
- Agent API — invoke agents from external Python/Java/REST clients

**Official Resources:**
- Website: https://www.salesforce.com/agentforce/
- MCP Support: https://www.salesforce.com/agentforce/mcp-support/
- Developer Docs: https://developer.salesforce.com/docs/einstein/genai/guide/get-started-agents.html
- Agent API: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-api.html

---

## Extension Points

Three integration tracks — use the one that fits your org's readiness:

### Track A: Native MCP Client ⭐ (Pilot July 2025 / Beta October 2025)

Agentforce now includes a native MCP (Model Context Protocol) client. Register any MCP server — including Neo4j's — and it becomes available as agent tools with no custom code.

```
Setup → Agents → MCP Servers → New
  Name: Neo4j Knowledge Graph
  Server URL: https://your-neo4j-mcp-server:8080/sse
  Auth: Bearer token (via Named Credential)
```

Run the Neo4j MCP server as an HTTP service:

```bash
# Official Neo4j MCP server (HTTP transport)
docker run -p 8080:8080 \
  -e NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687 \
  -e NEO4J_USERNAME=companies \
  -e NEO4J_PASSWORD=companies \
  neo4j/mcp \
  --neo4j-transport-mode http --host 0.0.0.0 --port 8080

# OR labs Python server (SSE transport)
pip install mcp-neo4j-cypher
NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687 \
NEO4J_USERNAME=companies \
NEO4J_PASSWORD=companies \
python -m mcp_neo4j_cypher --transport sse --port 8080
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                  Salesforce AgentForce                      │
│  ┌──────────────┐    ┌──────────────────────────────────┐   │
│  │    Agent     │    │   Atlas Reasoning Engine (ARE)   │   │
│  │              │───▶│   Plan → Act → Observe → Decide  │   │
│  │  Topics:     │    └──────────────┬───────────────────┘   │
│  │  - Research  │                   │                        │
│  │  - Industry  │          ┌────────▼─────────┐             │
│  │  - News      │          │  MCP Client      │             │
│  └──────────────┘          │  (Native Pilot)  │             │
└───────────────────────────┬──────────────────┬─────────────┘
                            │ MCP Protocol     │ Named Credential
                            │ (SSE/HTTP)       │ Bearer Token
                            ▼                  │
┌────────────────────────────────────────────┐ │
│         Neo4j MCP Server                   │◀┘
│  ┌────────────────────────────────────┐    │
│  │ Tools:                             │    │
│  │  • read_neo4j_cypher               │    │
│  │  • get_neo4j_schema                │    │
│  │  • graph algorithm execution       │    │
│  └────────────────────────────────────┘    │
│  Transport: HTTP SSE or Streamable HTTP    │
└─────────────────────────┬──────────────────┘
                          │ Bolt Protocol
                          ▼
┌────────────────────────────────────────────┐
│         Neo4j Database                     │
│  demo.neo4jlabs.com:7687 (companies DB)    │
│                                            │
│  Organizations ──[:IN_INDUSTRY]──▶ Industry│
│  Organizations ──[:LOCATED_IN]──▶ Location │
│  Articles ──[:MENTIONS]──▶ Organization    │
│  Articles ──[:HAS_CHUNK]──▶ Chunk          │
│                           (vector indexed) │
└────────────────────────────────────────────┘
```

### Track B: External Service Actions ⭐ (Spring 2025 GA — Most Stable)

Deploy a REST adapter (FastAPI) and import its OpenAPI spec into Salesforce External Services. Zero Apex code — fully declarative.

```bash
# 1. Deploy bridge server
git clone ...
cd examples
pip install -r requirements.txt
cp .env.example .env  # edit with your credentials
uvicorn mcp_bridge_server:app --port 8080

# 2. Get OpenAPI spec (Salesforce-ready)
curl http://localhost:8080/openapi.json > neo4j_openapi.json

# 3. Import into Salesforce External Services
# Setup → Integrations → External Services → New
# → Upload neo4j_openapi.json
# → Select operations to expose as agent actions
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                  Salesforce AgentForce                      │
│  ┌──────────────┐    ┌──────────────────────────────────┐   │
│  │    Agent     │    │   Atlas Reasoning Engine (ARE)   │   │
│  │              │───▶│                                  │   │
│  │  Topic:      │    └──────────────┬───────────────────┘   │
│  │  Company     │                   │ External Service Action│
│  │  Research    │          ┌────────▼─────────┐             │
│  └──────────────┘          │ Named Credential │             │
│                            │ "Neo4j_KG_API"   │             │
│                            │ X-Api-Key: ***   │             │
└───────────────────────────┬──────────────────┬─────────────┘
                            │ HTTPS POST       │
                            │ /research/company│
                            ▼                  │
┌────────────────────────────────────────────┐ │
│  Neo4j REST Bridge (FastAPI)               │◀┘
│  mcp_bridge_server.py                      │
│                                            │
│  Endpoints:                                │
│  POST /research/company     ← combined     │
│  POST /tools/query_company                 │
│  POST /tools/search_companies              │
│  POST /tools/search_news                   │
│  POST /tools/find_influential_companies    │
│  GET  /tools/list_industries               │
│  GET  /openapi.json  ← import to SF        │
│                                            │
│  Deploy: Heroku / Cloud Run / Railway      │
└─────────────────────────┬──────────────────┘
                          │ neo4j Python driver
                          │ Bolt protocol
                          ▼
┌────────────────────────────────────────────┐
│         Neo4j Database                     │
│  demo.neo4jlabs.com:7687 (companies DB)    │
└────────────────────────────────────────────┘
```

### Track C: Apex Actions (Maximum Flexibility)

Write Apex classes with `@InvocableMethod` annotations. These become agent actions with full access to Salesforce platform features (CRM records, flows, etc.).

```apex
@InvocableMethod(
    label='Research Company in Knowledge Graph'
    description='Retrieves company profile, news, and relationships from Neo4j. Use when user asks about a specific company.'
    category='Neo4j Knowledge Graph'
)
public static List<ResearchOutput> researchCompany(List<ResearchInput> inputs) {
    // calls Neo4jService.researchCompany() which uses Named Credential
}
```

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                  Salesforce AgentForce                      │
│                                                             │
│  Agent → ARE → selects "Research Company in KG" action      │
│                        │                                    │
│               ┌────────▼─────────────────────────────┐     │
│               │  Neo4jAction.cls (@InvocableMethod)   │     │
│               │  - Validates input                    │     │
│               │  - Calls Neo4jService.cls             │     │
│               │  - Formats output for ARE             │     │
│               └────────┬─────────────────────────────┘     │
│                        │                                    │
│               ┌────────▼─────────────────────────────┐     │
│               │  Neo4jService.cls (HTTP callout)      │     │
│               │  callout:Neo4j_KG_API/research/co..   │     │
│               │  Named Credential handles auth        │     │
│               └────────┬─────────────────────────────┘     │
└────────────────────────┼────────────────────────────────────┘
                         │ HTTPS (Named Credential)
                         ▼
              ┌──────────────────────────┐
              │  Neo4j REST Bridge       │
              │  (or direct Neo4j HTTP)  │
              └────────────┬─────────────┘
                           │
                           ▼
              ┌──────────────────────────┐
              │  Neo4j Database          │
              └──────────────────────────┘
```

---

## MCP Authentication

✅ **API Keys** — Custom header in Named Credential (`X-Api-Key: your-key`)

✅ **OAuth 2.0 Client Credentials** — M2M server-to-server via Connected App

✅ **JWT Bearer** — Server-to-server with certificate-based auth

✅ **MCP Bearer Token** — For native MCP client (Named Credential → MCP server)

**Named Credential Setup for API Key Auth:**
```
Setup → Security → External Credentials → New
  Label: Neo4j API Auth
  Protocol: Custom
  Principal: Named
  Custom Header: X-Api-Key = {your-bridge-api-key}

Setup → Security → Named Credentials → New
  Label: Neo4j_KG_API
  URL: https://your-neo4j-bridge.example.com
  External Credential: Neo4j API Auth
```

**Reference**: [mcp-auth-support.md](../mcp-auth-support.md#7-salesforce-agentforce)

---

## Industry Research Agent — Implementation

### Scenario

The **Industry Research Agent** queries the Neo4j Company News Knowledge Graph (250k entities) to provide:
1. Company profiles (industry, location, leadership)
2. Semantic news search (vector similarity over article embeddings)
3. Organizational relationship mapping
4. Network influence analysis (PageRank)
5. Full investment research report synthesis

### Dataset

**Company News Knowledge Graph (Demo Access):**
```python
NEO4J_URI      = "neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_USERNAME = "companies"
NEO4J_PASSWORD = "companies"
NEO4J_DATABASE = "companies"
```

**Data Model:**
```
(:Organization)-[:IN_INDUSTRY]->(:Industry / :IndustryCategory)
(:Organization)-[:LOCATED_IN]->(:Location)
(:Person)-[:WORKS_FOR]->(:Organization)
(:Article)-[:MENTIONS]->(:Organization)
(:Article)-[:HAS_CHUNK]->(:Chunk)  ← vector indexed ('news' index)
```

### Track A: Native MCP — Agent Configuration

```yaml
# AgentForce Agent Configuration (Agent Builder)
Agent:
  Name: Industry Research Agent
  Description: Investment research assistant using Neo4j knowledge graph
  Model: claude-3-5-sonnet (via Bedrock BYOM) or gpt-4o (default)

Topics:
  - Name: Company Research
    Description: >
      Handles requests to research specific companies, find company profiles,
      leadership information, industry classification, and organizational
      relationships from the Neo4j knowledge graph.
      Does NOT handle contract, billing, or Salesforce CRM data questions.
    Instructions: |
      Always return company_id when looking up companies.
      Search for news when discussing recent developments.
      Use relationship analysis for competitive intelligence.
    Actions:
      - Neo4j MCP: read_neo4j_cypher (company lookup queries)
      - Neo4j MCP: get_neo4j_schema (understand data model)

  - Name: Industry Analysis
    Description: >
      Handles requests about industry sectors, market trends, competitive
      landscape, and identifying key players within a sector.
    Actions:
      - Neo4j MCP: read_neo4j_cypher (industry queries)

  - Name: News Research
    Description: >
      Finds and analyzes news articles, recent developments, and events
      related to companies or industries in the knowledge graph.
    Actions:
      - Neo4j MCP: read_neo4j_cypher (news/article queries)
```

**Sample Cypher queries for MCP tools:**
```cypher
-- Company profile
MATCH (o:Organization {name: $company})
RETURN o.name as name,
       o.id as company_id,
       [(o)-[:IN_INDUSTRY]->(i:Industry) | i.name] as industries,
       [(o)-[:LOCATED_IN]->(l:Location) | l.name] as locations,
       [(o)<-[:WORKS_FOR]-(p:Person) | {name: p.name, title: p.title}] as leadership
LIMIT 1

-- Recent news
MATCH (o:Organization {name: $company})<-[:MENTIONS]-(a:Article)
RETURN a.id as article_id, a.title as title,
       toString(a.date) as date, a.sentiment as sentiment
ORDER BY a.date DESC LIMIT 5

-- PageRank (requires GDS plugin)
CALL gds.pageRank.stream('companies')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name as company, score
ORDER BY score DESC LIMIT 10
```

### Track B: External Service — Python Setup

```python
# Install and run the bridge server
pip install -r examples/requirements.txt
cp examples/.env.example examples/.env
# Edit .env with your Neo4j + API key credentials

uvicorn examples.mcp_bridge_server:app --port 8080

# Test the API
curl -X POST http://localhost:8080/research/company \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: your-key" \
  -d '{"company_name": "Apple"}'

# Get Salesforce-importable OpenAPI spec
curl http://localhost:8080/openapi.json
```

**Salesforce setup (3 steps, no code):**
```
Step 1: Named Credential
  Setup → Security → Named Credentials → New
  URL: https://your-bridge.example.com
  Auth: Custom header X-Api-Key

Step 2: External Service
  Setup → Integrations → External Services → New
  Upload: openapi_spec.json (or paste /openapi.json URL)
  Select operations to expose

Step 3: Agent Actions
  Setup → Agents → Your Agent → Topics → New Topic
  Add Actions from External Service: researchCompany, searchCompanies, etc.
```

### Track C: Apex — Deploy and Register

```bash
# Deploy Apex to your Salesforce org via SFDX
sf project deploy start \
  --source-dir examples/apex/ \
  --target-org your-sandbox-alias

# Run tests
sf apex run test \
  --class-names Neo4jServiceTest \
  --result-format human \
  --target-org your-sandbox-alias

# Register in Agent Builder:
# Setup → Agents → Actions → New Action → Apex
# Select: Neo4jAction → researchCompany method
```

### Multi-Agent Architecture (Advanced)

```
┌──────────────────────────────────────────────────────────┐
│                 Research Coordinator Agent                │
│          (AgentForce Agent: orchestrates workflow)        │
└──────────────┬────────────────────┬──────────────────────┘
               │                    │
    ┌──────────▼──────────┐  ┌──────▼──────────────────────┐
    │  Database Agent     │  │    Analysis Agent            │
    │                     │  │                              │
    │  Actions:           │  │  Actions:                    │
    │  - researchCompany  │  │  - Prompt Template           │
    │  - searchCompanies  │  │    (synthesis + report)      │
    │  - listIndustries   │  │  - CRM record write          │
    │  - influential cos  │  │    (save findings)           │
    └──────────┬──────────┘  └──────────────────────────────┘
               │
    ┌──────────▼──────────┐
    │   Neo4j Knowledge   │
    │   Graph             │
    │   (via MCP or REST) │
    └─────────────────────┘
```

### Python Client — Drive the Agent Externally

```python
# Install: pip install salesforce-agentforce requests
from examples.agentforce_agent import run_industry_research_agent

# Run full research workflow
result = run_industry_research_agent("Apple", verbose=True)
print(result["final_report"])
```

---

## Salesforce Developer Environment Setup

> **New to Salesforce?** See [AGENTFORCE.md](./AGENTFORCE.md#getting-started) for step-by-step onboarding.

**Quick start:**
1. Create free Developer Edition org: https://developer.salesforce.com/signup
2. Enable AgentForce: Setup → Einstein Setup → Turn on Einstein
3. Install SFDX CLI: https://developer.salesforce.com/tools/salesforcecli
4. Login: `sf org login web --set-default-dev-hub`

---

## Challenges and Gaps

### Current Limitations

1. **Native MCP in Pilot** (Track A)
   - Not yet GA — requires opt-in to Salesforce pilot program
   - May not be available in Developer Edition orgs (needs production/sandbox)
   - Severity: Moderate (use Track B/C as fallback)

2. **Apex Callout Limit: 10 per Transaction** (Track C)
   - Cannot chain more than 10 Neo4j HTTP calls in a single Apex transaction
   - ARE's sequential action execution multiplies this across turns
   - Severity: Moderate — mitigated by combined `/research/company` endpoint

3. **Action Output Truncation by ARE**
   - ARE truncates action outputs at ~2000 tokens
   - Large graph query results (50+ nodes) will be silently cut off
   - Severity: Moderate — design APIs to return top-5 concise results

4. **No Parallel Action Execution**
   - ARE executes actions sequentially, not in parallel
   - Multi-step research (profile → news → relationships) is 3x slower
   - Severity: Low — combined endpoint pattern mitigates this

5. **Session Context Not Persisted**
   - Sessions expire after 5 min inactivity (configurable to 60 min)
   - No built-in cross-session memory
   - Severity: Low for demo, Moderate for production research tools

6. **External Service OAS Constraints**
   - Only OAS 3.0 (not Swagger 2.x)
   - Complex nested objects may not parse correctly
   - No streaming support
   - Severity: Low — keep spec flat and simple

### Workarounds

**For callout limit**: Use the combined `/research/company` endpoint that returns profile + news + relationships in one call.

**For output truncation**: Structure Neo4j responses as concise JSON arrays (max 5 items), use `summary` fields instead of full `content`.

**For session persistence**: Write research findings to a Salesforce custom object via an Apex action at end of session.

---

## Additional Integration Opportunities

### 1. Agent Memory with Neo4j

Use `mcp-neo4j-memory` to store research findings as graph nodes:
- Sessions write entities and relationships to Neo4j
- Cross-session context via graph traversal
- See: https://github.com/neo4j-labs/agent-memory

### 2. Salesforce CRM Enrichment

Agent discovers company info in Neo4j → writes enriched data to Salesforce Account objects:
```apex
Account acc = [SELECT Id, Name FROM Account WHERE Name = :companyName LIMIT 1];
acc.Neo4j_Industries__c = extractedIndustries;
acc.Neo4j_Last_Enriched__c = DateTime.now();
update acc;
```

### 3. AgentExchange Packaging

Package this integration as:
- A managed AppExchange package (pre-configured Named Credentials, External Service, sample Topics)
- An AgentExchange MCP server listing (when the marketplace opens)

### 4. Graph Algorithms for Sales Intelligence

Expose GDS algorithms as agent actions:
- **PageRank** — identify most influential prospects
- **Community Detection** — find industry clusters for ABM
- **Shortest Path** — find connection paths to prospects via mutual contacts

---

## Code Examples

See the `examples/` directory:

| File | Description | Track |
|------|-------------|-------|
| `neo4j_tools.py` | All 11 reference agent tool functions | All |
| `mcp_bridge_server.py` | FastAPI REST adapter (auto-generates OpenAPI spec) | B |
| `agentforce_agent.py` | Python client using AgentForce Agent API | All |
| `apex/Neo4jService.cls` | Apex HTTP callout service | C |
| `apex/Neo4jAction.cls` | Apex @InvocableMethod actions | C |
| `apex/Neo4jServiceTest.cls` | Apex test class (75%+ coverage) | C |
| `metadata/openapi_spec.json` | OpenAPI 3.0 spec for External Service import | B |
| `requirements.txt` | Python dependencies | A, B |
| `Dockerfile` / `Procfile` | Container / Heroku deployment | B |

---

## Resources

- **AgentForce Developer Docs**: https://developer.salesforce.com/docs/einstein/genai/guide/get-started-agents.html
- **Agent API Reference**: https://developer.salesforce.com/docs/ai/agentforce/guide/agent-api.html
- **External Service Actions**: https://developer.salesforce.com/blogs/2025/05/call-third-party-apis-from-an-agent-with-external-service-actions
- **MCP Support**: https://developer.salesforce.com/blogs/2025/06/introducing-mcp-support-across-salesforce
- **Python SDK (PyPI)**: https://pypi.org/project/salesforce-agentforce/
- **Neo4j MCP Official**: https://github.com/neo4j/mcp
- **Neo4j MCP Labs**: https://github.com/neo4j-contrib/mcp-neo4j
- **Demo Database**: neo4j+s://demo.neo4jlabs.com:7687 (companies/companies)
- **BYOM Guide**: https://developer.salesforce.com/blogs/2024/10/build-generative-ai-solutions-with-llm-open-connector

## Status

- ✅ MCP integration (Pilot July 2025, Beta October 2025)
- ✅ External Service Actions (Spring 2025 GA)
- ✅ Apex Actions
- ✅ Python Agent API client (`pip install salesforce-agentforce`)
- ✅ OAuth 2.0 Client Credentials + JWT Bearer
- ⚠️ Native MCP not yet GA (Pilot program required)
- ⚠️ Apex callout limits require API design consideration

**Effort Score**: 7.8/10 (Salesforce platform learning curve is steep)
**Impact Score**: 7.9/10 (250k+ Salesforce orgs, deep CRM integration)
