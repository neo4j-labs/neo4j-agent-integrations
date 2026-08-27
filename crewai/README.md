# CrewAI + Neo4j Agent Integrations

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CrewAI](https://img.shields.io/badge/CrewAI-v1.15+-orange.svg)](https://www.crewai.com/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.x%20%7C%20Aura-008CC1.svg)](https://neo4j.com/)
[![NAMS Memory](https://img.shields.io/badge/NAMS-Memory-green.svg)](https://memory.neo4jlabs.com/)
[![MCP Ready](https://img.shields.io/badge/MCP-Enabled-purple.svg)](https://modelcontextprotocol.io/)

Production-grade multi-agent orchestration with **CrewAI**, integrated with the **Neo4j Knowledge Graph**, **Neo4j Agent Memory Server (NAMS)** for cross-session long-term context, and **Model Context Protocol (MCP)** tool discovery with Aura OAuth support.

---

## Architecture Overview

This integration demonstrates how specialized AI agents collaborate sequentially to research, analyze, and synthesize deep graph intelligence from Neo4j without hallucinations.

```mermaid
flowchart TD
    subgraph Client["User & Client Layer"]
        CLI["CLI (main.py)"]
        API["FastAPI REST Server (server.py)"]
    end

    subgraph CrewAI["CrewAI Multi-Agent Orchestrator"]
        Researcher["🔍 Lead Knowledge Graph Researcher\n(Extracts entities, leadership, industries)"]
        Analyst["📊 Strategic Market & Graph Analyst\n(Analyzes multi-hop graph paths & risk)"]
        Writer["✍️ Executive Intelligence Briefing Author\n(Synthesizes findings into Markdown briefs)"]
        
        Researcher -->|Structured Graph Facts| Analyst
        Analyst -->|Network & Ecosystem Insights| Writer
    end

    subgraph DataLayer["Data & Knowledge Layer"]
        Neo4j[("Neo4j Knowledge Graph\n(Companies & Ecosystem DB)")]
        NAMS[("Neo4j Agent Memory (NAMS)\n(Cross-Session Shared Graph Memory)")]
        MCPServer["MCP Server (Optional)\n(Hosted Aura MCP / Official Neo4j MCP)"]
    end

    CLI --> CrewAI
    API --> CrewAI

    Researcher <-->|"Cypher & Full-Text Search"| Neo4j
    Analyst <-->|"Multi-Hop Graph Traversal"| Neo4j
    Writer <-->|"Preferences & Fact Storage"| NAMS
    
    Researcher -.->|"Dynamic Tools"| MCPServer
    Analyst -.->|"Dynamic Tools"| MCPServer
```

---

## Key Capabilities

1. **Multi-Agent Orchestration & Task Delegation**:
   - **Researcher Agent**: Executes parameterized Cypher queries and full-text index lookups for organizations, leadership rosters, and sector taxonomies.
   - **Analyst Agent**: Traverses multi-hop relationship paths (`o1-[*1..2]-o2`) to uncover hidden corporate ties, investor networks, and supply chain dependencies.
   - **Writer Agent**: Formats the final executive intelligence briefing, recalls formatting guidelines from memory, and commits key analytical takeaways.

2. **Neo4j Knowledge Graph Tools**:
   - `search_companies`: Full-text Lucene index search with automatic fallback.
   - `query_company_profile`: Enriched company metadata, locations, and executive/board leadership.
   - `analyze_company_relationships`: Multi-hop path exploration with cycle prevention and depth clamping.
   - `run_cypher_query`: Safe, read-only Cypher query execution with injection protection.
   - `list_industry_categories`: Sector taxonomy inspection.

3. **Neo4j Agent Memory (NAMS) Integration**:
   - Cross-session memory and shared context graph across all crew members.
   - Tools: `search_memory`, `save_memory_fact`, and `get_preferences`.
   - Allows agents to remember prior analyses and adapt to user reporting preferences.

4. **Model Context Protocol (MCP) Support**:
   - Auto-detection of HTTP / Streamable HTTP, SSE, and Stdio transports.
   - **OAuth 2.0 Client Credentials Grant** support with RFC 9728 dynamic discovery for hosted Neo4j Aura MCP endpoints.
   - Resilient non-fatal fallback if external MCP servers are offline.

5. **Production Deployment Options**:
   - CLI execution script (`main.py`).
   - Production FastAPI application (`server.py`) with OpenAPI documentation.
   - Taskfile automation for developer workflows (`Taskfile.yml`).

---

## Memory Flow (NAMS)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Writer as Writer Agent
    participant MemoryTools as NAMS Memory Tools
    participant NAMS as Neo4j Agent Memory (NAMS)
    participant Neo4j as Neo4j Graph DB

    User->>Writer: "Generate intelligence brief for Google"
    Writer->>MemoryTools: get_preferences(category="reporting")
    MemoryTools->>NAMS: search_preferences("reporting")
    NAMS-->>Writer: "Format with executive summary and risk matrices"
    
    Note over Writer: Synthesizes final report using preference
    
    Writer->>MemoryTools: save_memory_fact(subject="Google", predicate="expansion", content="Deep AI investments")
    MemoryTools->>NAMS: add_fact(...)
    NAMS->>Neo4j: Persist fact to knowledge graph
    NAMS-->>Writer: Fact stored successfully
    Writer-->>User: Delivers customized intelligence briefing
```

---

## MCP Architecture & Aura OAuth Flow

```mermaid
flowchart LR
    subgraph AgentRuntime["CrewAI Agent Runtime"]
        Agent["CrewAI Agent"]
        MCPClient["agent/mcp.py Client"]
    end

    subgraph AuraAuth["Neo4j Aura OAuth 2.0"]
        Discovery["RFC 9728 Discovery\n/.well-known/oauth-protected-resource"]
        TokenEndpoint["Aura Token Endpoint\n/oauth/token"]
    end

    subgraph MCPEndpoint["Hosted MCP Service"]
        AuraMCP["Hosted Aura MCP Server\n(Streamable HTTP / SSE)"]
    end

    Agent -->|Execute MCP Tool| MCPClient
    MCPClient -->|1. Discover Token URL| Discovery
    MCPClient -->|2. Client Credentials Grant| TokenEndpoint
    TokenEndpoint -->>|3. Bearer Access Token| MCPClient
    MCPClient -->|4. Tool Request with Bearer Token| AuraMCP
    AuraMCP -->>|5. Tool Results| Agent
```

---

## Quick Start

### 1. Prerequisites
- Python 3.10+
- OpenAI API Key (or any LiteLLM-supported provider key)
- Neo4j Database (public demo DB provided by default)

### 2. Installation

Clone repository and navigate to `crewai/`:

```bash
cd crewai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Alternatively, with [Task](https://taskfile.dev/):
```bash
task install
```

### 3. Configure Environment

Copy `.env.example` to `.env` and set your credentials:

```bash
cp .env.example .env
```

```ini
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL_NAME=gpt-4o-mini

# Pre-configured public demo database:
NEO4J_URI=neo4j+s://demo.neo4jlabs.com:7687
NEO4J_USERNAME=companies
NEO4J_PASSWORD=companies
NEO4J_DATABASE=companies
```

### 4. Run the Crew

Run a complete company intelligence workflow:

```bash
python main.py --company "Google" --output "google_brief.md"
```

Or via Taskfile:
```bash
task run -- "Microsoft"
```

---

## Running Tests

Run the comprehensive pytest test suite covering Neo4j tools, NAMS memory, MCP integration, and multi-agent crew orchestration:

```bash
task test
# or
pytest -vv tests/
```

---

## Production Deployment

### 1. FastAPI REST Server

Start the production API server:

```bash
task server
# or
uvicorn server:app --host 0.0.0.0 --port 8000
```

Trigger research runs programmatically:

```bash
curl -X POST http://localhost:8000/api/v1/research \
  -H "Content-Type: application/json" \
  -d '{"company_name": "Apple", "output_file": "apple_report.md"}'
```

### 2. Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Resources

- **CrewAI Documentation**: https://docs.crewai.com/
- **Neo4j Agent Memory (NAMS)**: https://memory.neo4jlabs.com/
- **Neo4j Official Website**: https://neo4j.com/
- **Model Context Protocol**: https://modelcontextprotocol.io/

