# DataRobot + Neo4j Integration

## Overview

This integration packages a **Neo4j-backed research agent** as a DataRobot **Agentic Workflow** custom model.  
It supports three optional extensions — all non-blocking if not configured:

| Extension | Purpose | Config var |
|---|---|---|
| **Neo4j Agent Memory (NAMS)** | Cross-session memory backed by a knowledge graph | `MEMORY_API_KEY`, `MEMORY_WORKSPACE_ID` |
| **MCP (Model Context Protocol)** | Dynamically load tools from any MCP server | `MCP_SERVER_URL` |

---

## Architecture

```mermaid
flowchart TD
    User(["👤 User / DataRobot Playground / API Client"])

    subgraph DR["DataRobot Platform"]
        DRUM["DRUM Runtime\n(custom model)"]
        ENTRY["custom.py\nload_model() · chat()"]
    end

    subgraph Agent["Neo4j Research Agent (agent.py)"]
        LOOP["OpenAI Tool-Calling Loop"]
        BUILTIN["10 Built-in Neo4j Tools\nsearch_companies · query_company\nanalyze_relationships · search_news\npeople_at_company · …"]
        MCPTOOLS["MCP Tools (dynamic)\nloaded from MCP server at startup"]
    end

    subgraph MCP["MCP Layer (mcp_client.py) — optional"]
        MCPSRV["Any MCP Server\n(NAMS MCP · Neo4j MCP · custom)"]
    end

    subgraph Memory["Neo4j Agent Memory (memory.py) — optional"]
        STM["Short-Term Memory\nConversation history"]
        LTM["Long-Term Memory\nEntities · Knowledge Graph"]
    end

    subgraph Neo4j["Neo4j Companies Graph"]
        KG["Organizations · People\nArticles · Industries"]
    end

    User -->|"POST /chat"| DRUM --> ENTRY

    ENTRY -->|"1 · get_context()"| Memory
    Memory -->|"past context"| ENTRY

    ENTRY -->|"2 · run agent"| LOOP
    LOOP <-->|"built-in tool calls"| BUILTIN <-->|"Cypher"| KG
    LOOP <-->|"MCP tool calls"| MCPTOOLS <-->|"call_tool()"| MCPSRV

    LOOP -->|"final answer"| ENTRY
    ENTRY -->|"3 · save_turn()"| Memory

    ENTRY -->|"OpenAI-compatible response"| User
```

---

## Files

```
datarobot/
├── .env.example
├── README.md
├── requirements.txt
├── run_local.py            ← local CLI test (mirrors DataRobot execution)
├── datarobot_agent.ipynb   ← Jupyter demo notebook
├── agent/
│   ├── __init__.py
│   ├── agent.py            ← Neo4jResearchAgent + 10 tools + MCP tool loader
│   ├── custom.py           ← DataRobot load_model() + chat() with memory
│   ├── helpers.py          ← prompt helpers + response formatting
│   ├── memory.py           ← NAMS integration (graceful no-op if absent)
│   ├── mcp_client.py       ← MCP client (graceful no-op if absent/unconfigured)
│   ├── model-metadata.yaml ← DataRobot runtime parameter definitions
│   └── requirements.txt    ← deps bundled in DataRobot ZIP
└── infra/
    ├── __init__.py
    └── agent.py            ← ZIP packager + DataRobot API validator
```

---

## Quick Start (local)

```bash
cd datarobot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in OPENAI_API_KEY; optionally MEMORY_API_KEY and MCP_SERVER_URL
python run_local.py "Give me a competitive snapshot of Google"
```

---

## Neo4j Agent Memory (NAMS)

```bash
# Get a free key at https://memory.neo4jlabs.com
MEMORY_API_KEY=nams_... MEMORY_WORKSPACE_ID=<workspace-id> python run_local.py "Tell me about Apple"
# Next session will have context from the first one
```

How it works in `custom.py`:

| Step | Action |
|---|---|
| Request arrives | `session_id` derived from `user` field or hash of first message |
| Pre-run | `memory.get_context()` fetches relevant past-session context from NAMS |
| Context found | Prepended as a `system` message so the LLM knows prior interactions |
| Post-run | `memory.save_turn()` persists user message + response to NAMS |

Memory is **non-blocking** — if `MEMORY_API_KEY` is absent or the package is not installed, every call is a silent no-op.

> **`MEMORY_WORKSPACE_ID`** — set this to the workspace ID portion of your NAMS key (e.g. `nams_<WORKSPACE_ID>_<secret>`). The NAMS SDK reads it from the `MEMORY_WORKSPACE_ID` env var and sends it as the `X-Workspace-Id` header to scope all memory to your workspace.

---

## MCP Integration

When `MCP_SERVER_URL` is set, the agent **discovers tools dynamically** from the MCP server at startup and makes them available to the LLM alongside the built-in Neo4j tools.

```bash
# Example: connect to NAMS MCP server (16 memory tools)
uvx "neo4j-agent-memory[mcp]" mcp serve --password <neo4j-password> &
MCP_SERVER_URL=http://localhost:8080/sse python run_local.py "What do you know about me?"

# Example: HTTP/SSE MCP server
MCP_SERVER_URL=http://localhost:3001/sse python run_local.py "..."

# Example: stdio MCP server
MCP_SERVER_URL="uvx my-mcp-server serve" python run_local.py "..."
```

Supported transports:
- **HTTP / SSE** — any URL starting with `http://` or `https://`
- **stdio** — any other string treated as a shell command

MCP is **non-blocking** — if `MCP_SERVER_URL` is absent or the `mcp` package is not installed, the agent runs with its 10 built-in tools only.

---

## Built-in Neo4j tools

| Tool | Description |
|---|---|
| `search_companies` | Full-text company lookup |
| `list_industries` | List all industry categories |
| `companies_in_industry` | Companies in a specific industry |
| `query_company` | Company profile — summary, industries, locations, leadership |
| `analyze_relationships` | Org-to-org graph traversal (depth 1–4) |
| `people_at_company` | Executives and board members |
| `search_news` | Semantic news search (vector similarity) |
| `articles_in_month` | Articles published in a given month |
| `get_article` | Full article body by article_id |
| `companies_in_article` | Organizations mentioned in an article |

---

## DataRobot packaging & deployment

```bash
# Package
python infra/agent.py package
# → dist/neo4j_datarobot_agent.zip  (includes memory.py + mcp_client.py)

# Validate API access
python infra/agent.py validate
```

**Upload steps:**
1. DataRobot → **Workshop** → **Custom Models** → **Add custom model** → Upload files
   *(In some DataRobot versions the path is: **Model Registry** → **Custom Models** → **Create custom model**)*
2. Upload all files from `dist/neo4j_datarobot_agent.zip` (or upload the ZIP directly)
3. Set **Target Type** = `Agentic Workflow`
4. Set runtime parameters (table below)
5. Click **Test** to verify, then **Register model** → **Deploy**

---

## Runtime parameters

| Parameter | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | _(required)_ |
| `OPENAI_MODEL` | Chat model | `gpt-4o-mini` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `NEO4J_URI` | Neo4j connection string | `neo4j+s://demo.neo4jlabs.com:7687` |
| `NEO4J_USERNAME` | Neo4j username | `companies` |
| `NEO4J_PASSWORD` | Neo4j password | _(required)_ |
| `NEO4J_DATABASE` | Neo4j database | `companies` |
| `MEMORY_API_KEY` | NAMS key — leave blank to disable memory | _(optional)_ |
| `MEMORY_WORKSPACE_ID` | NAMS workspace ID (the segment between the first two underscores in your key: `nams_<WORKSPACE_ID>_...`) — required when using NAMS | _(optional)_ |
| `MCP_SERVER_URL` | MCP server URL — leave blank to skip MCP | _(optional)_ |
| `AGENT_MAX_TOOL_STEPS` | Max tool-call iterations | `6` |

---

## Notes

- Secrets are loaded from DataRobot runtime parameters first; `.env` is for local development only.
- `neo4j-agent-memory` and `mcp` both require Python ≥ 3.10. DataRobot's runtime satisfies this. On Python 3.9 locally both features silently disable themselves.
- `infra/agent.py validate` requires direct access to `app.datarobot.com`. Corporate proxies (Zscaler) return HTTP 403 — run from a network-open machine.
