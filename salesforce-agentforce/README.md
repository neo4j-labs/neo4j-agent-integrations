# Salesforce Agentforce + Neo4j Integration

## Overview

**Salesforce Agentforce** is Salesforce's enterprise AI agent platform powered by the **Atlas Reasoning Engine (ARE)** — a ReAct-style orchestration loop that plans, selects tools, observes results, and iterates to answer user queries.

**Key Features:**
- Atlas Reasoning Engine (plan → act → observe → decide loop)
- Topics (semantic routing layer) + Actions (tool execution layer)I 
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

### Track A: Native MCP Client (Pilot July 2025, Beta October 2025, GA April 2026)

Agentforce now includes a native MCP (Model Context Protocol) client. Register any MCP server — including Neo4j's — and it becomes available as agent tools with no custom code.

```
Setup → Agents → MCP Servers → New
  Name: Neo4j Knowledge Graph
  Server URL: https://mcp.demo.neo4jlabs.com/mcp
  Auth: Bearer token (via Named Credential)
```

Run the Neo4j MCP server as an HTTP service:

```bash
# Official Neo4j MCP docker images (HTTP transport)
docker run -p 8080:8080 \
  -e NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687 \
  -e NEO4J_DATABASE=companies \
  mcp/neo4j \
  --neo4j-transport-mode http \
  --neo4j-http-host 0.0.0.0 --neo4j-http-port 8000

# OR Official Neo4j MCP binary (https://github.com/neo4j/mcp/releases)
./neo4j-mcp \
    --neo4j-uri "neo4j+s://demo.neo4jlabs.com:7687" \
    --neo4j-database "companies" \
    --neo4j-transport-mode "http" --neo4j-http-port 8080

# OR user demo server (https://mcp.demo.neo4jlabs.com/mcp)
```

⚠️ When setting up the Neo4j MCP server in HTTP transport mode, the credentials are provided per-request via Basic Auth headers. 
Neo4j username and password should not be set (as environment variables or parameters) for HTTP transport mode;

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

Use the Query API, which allows to execute Cypher statements against a Neo4j server through HTTP requests.

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

curl -X 'POST' 'https://demo.neo4jlabs.com:7473/db/companies/query/v2' \
    -H 'content-type: application/json' \
    -H 'accept: application/json' \
    -H "Authorization: Basic Y29tcGFuaWVzOmNvbXBhbmllcw==" \
    -d '{"statement": "MATCH (o:Organization {name: \"Neo4j\"})-[:HAS_CEO]->(p:Person) RETURN p.name AS CEO"}'

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
    label='Get Neo4j Organization Insights' 
    description='Queries Neo4j for strategic insights about an organization, including competitors, suppliers, and geographic presence.')
    public static List<Response> getInsights(List<Request> requests) {
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
              │  Neo4j HTTP Query API    │
              └────────────┬─────────────┘
                           │
                           ▼
              ┌──────────────────────────┐
              │  Neo4j Database          │
              └──────────────────────────┘
```

---

## Salesforce Configuration



---

## Get company insights — Implementation

### Scenario

The **Industry Research Agent** queries the Neo4j Company News Knowledge Graph (250k entities) to provide:
1. Company profiles (industry, location, leadership)
2. Semantic news search (vector similarity over article embeddings)
3. Organizational relationship mapping
4. Competitors, suppliers and subsidiaries

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
(:Organization)-[:HAS_CEO]->(:Person)
(:Organization)-[:HAS_COMPETITOR|HAS_SUPPLIER|HAS_SUBSIDIARY]->(:Person)
(:Article)-[:MENTIONS]->(:Organization)
```

**Cypher query**
```cypher
MATCH (org:Organization {name: "Neo4j"})
OPTIONAL MATCH (org)-[:HAS_CEO]->(ceo:Person)

// 1. Get Network (Competitors, Suppliers, Subsidiaries) with their CEOs as complete nodes
WITH org, ceo,
     [(org)-[:HAS_COMPETITOR]-(comp) | {organization: comp, ceo: [(comp)-[:HAS_CEO]->(c) | c][0]}] AS competitors,
     [(org)-[:HAS_SUPPLIER]->(supp) | {organization: supp, ceo: [(supp)-[:HAS_CEO]->(c) | c][0]}] AS suppliers,
     [(org)-[:HAS_SUBSIDIARY]->(sub) | {organization: sub, ceo: [(sub)-[:HAS_CEO]->(c) | c][0]}] AS subsidiaries

// 2. Fetch exactly 10 articles mentioning any entity in the network
CALL (org, competitors, suppliers, subsidiaries) {
    WITH [c IN competitors | c.organization] + 
         [s IN suppliers | s.organization] + 
         [sub IN subsidiaries | sub.organization] + 
         [org] AS targets
    UNWIND targets AS target
    WITH DISTINCT target WHERE target IS NOT NULL
    MATCH (article:Article)-[:MENTIONS]->(target)
    RETURN DISTINCT article
    LIMIT 10
}

// 3. Return everything as complete nodes
RETURN 
    org, 
    ceo, 
    competitors, 
    suppliers, 
    subsidiaries, 
    collect(article) AS related_articles
```

### Track C: Apex Actions

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

---

## Code Examples

See the `examples/` directory:

| File | Description | Track |
|------|-------------|-------|
| `apex/*` | Apex files with tests | C |

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

