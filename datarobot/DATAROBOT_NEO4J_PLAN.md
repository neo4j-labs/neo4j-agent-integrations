# DataRobot + Neo4j Integration Plan

**Prepared:** May 2026

> **Implementation Note (updated June 2026):** The original plan explored LangGraph and CrewAI as agent frameworks.
> The final implementation uses the **direct OpenAI SDK** approach (Pattern A) — simpler, no LangGraph dependency,
> fewer moving parts, and fully portable across DataRobot environments. LangGraph-specific sections below are
> retained for reference only.  
**Repo:** neo4j-agent-integrations  
**Folder:** `datarobot/`

---

## 1. What is DataRobot?

DataRobot is an enterprise AI platform that spans the full lifecycle of ML and generative AI — from data preparation and model training through to deployment, monitoring, and governance. In the context of this integration, the relevant surface is **DataRobot Agentic AI**: the ability to build, test, and deploy AI agents as managed cloud services inside the DataRobot platform.

### Key characteristics

- **Enterprise-grade**: Used by large financial institutions, healthcare orgs, and industrial companies. Production governance and audit trails are first-class concerns.
- **Multi-framework support**: Agents can be written in LangGraph (default), CrewAI, LlamaIndex, or any custom Python framework using the "Generic Base" template.
- **DataRobot as the infrastructure layer**: Agents are packaged as DataRobot Custom Models, deployed as Deployments, and exposed via REST endpoints — all managed by DataRobot's infrastructure.
- **LLM Gateway**: A unified proxy that routes to any LLM provider (OpenAI, Azure OpenAI, Anthropic, AWS Bedrock, Google Vertex, self-hosted) without changing agent code. The agent just talks to the gateway endpoint.
- **MCP (Model Context Protocol) native support**: DataRobot has first-class MCP tooling — an `af-component-datarobot-mcp` library, a `datarobot-mcp-template`, and the ability to deploy an MCP server itself as a DataRobot Custom Model.

---

## 2. DataRobot Agentic AI Architecture

![Architecture](https://mermaid.ink/img/Z3JhcGggVEQKICAgIFVzZXIoWyJOb3RlYm9vayAvIEFwcCJdKSAtLT4gcGxheWdyb3VuZAoKICAgIHN1YmdyYXBoIGRyWyJEYXRhUm9ib3QgUGxhdGZvcm0iXQogICAgICAgIHBsYXlncm91bmRbIkFnZW50aWMgUGxheWdyb3VuZCAvIFJFU1QgQ2xpZW50Il0KICAgICAgICBiYWNrZW5kWyJGYXN0QVBJIEJhY2tlbmQKUG9ydCA4MDgwIl0KICAgICAgICBhZ2VudFsiQWdlbnQgQ3VzdG9tIE1vZGVsCkxhbmdHcmFwaCAvIENyZXdBSSJdCiAgICAgICAgbWNwWyJNQ1AgU2VydmVyCkN1c3RvbSBNb2RlbCJdCiAgICAgICAgZ2F0ZXdheVsiTExNIEdhdGV3YXkKR1BULTRvIC8gQ2xhdWRlIl0KCiAgICAgICAgcGxheWdyb3VuZCAtLT4gYmFja2VuZAogICAgICAgIGJhY2tlbmQgLS0-IGFnZW50CiAgICAgICAgYWdlbnQgLS0-fE1DUCBIVFRQIC0gUGF0dGVybiBCfCBtY3AKICAgICAgICBhZ2VudCAtLT4gZ2F0ZXdheQogICAgZW5kCgogICAgYWdlbnQgLS0-fG5lbzRqLWRyaXZlciAtIFBhdHRlcm4gQXwgbmVvNGpbKCJOZW80aiBBdXJhREIKQ29tcGFuaWVzIEtHIildCiAgICBtY3AgLS0-fG5lbzRqLWRyaXZlciAtIFBhdHRlcm4gQnwgbmVvNGoK)

```
┌─────────────────────────────────────────────────────────────┐
│                     DataRobot Platform                      │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────┐  │
│  │   Frontend   │   │  FastAPI     │   │  Agent Custom │  │
│  │  (React +    │◄─►│  Backend     │◄─►│  Model        │  │
│  │   @dr-ui)    │   │  Server      │   │  (LangGraph/  │  │
│  └──────────────┘   └──────────────┘   │  CrewAI/etc.) │  │
│        Port 5173         Port 8080     └──────┬────────┘  │
│                                               │            │
│                                      ┌────────▼────────┐  │
│                                      │  MCP Server     │  │
│                                      │  Custom Model   │  │
│                                      │  (Port 9000)    │  │
│                                      └────────┬────────┘  │
│                                               │            │
│                                      ┌────────▼────────┐  │
│                                      │  LLM Gateway    │  │
│                                      │  (GPT-4o,       │  │
│                                      │   Claude, etc.) │  │
│                                      └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Neo4j (AuraDB or │
                    │  self-hosted)     │
                    │  Companies KG     │
                    └───────────────────┘
```

### Component breakdown

| Component | What it is | How it maps to our integration |
|-----------|-----------|-------------------------------|
| **DataRobot CLI (`dr`)** | CLI tool for scaffolding, running, and deploying agents | `dr start` → `dr run dev` → `dr run deploy` |
| **Custom Model** | Containerised Python service — the agent lives here | `agent/custom.py` — implements `def chat(...)` |
| **Execution Environment** | Docker image with pre-cached dependencies | Built via Pulumi; includes `neo4j-driver`, `langchain-neo4j` |
| **LLM Gateway** | Unified LLM proxy inside DataRobot | Configured via `USE_DATAROBOT_LLM_GATEWAY=1` in `.env` |
| **MCP Server** | Separate Custom Model exposing tools via MCP protocol | Can expose Neo4j tools: `run_cypher`, `vector_search`, etc. |
| **Pulumi infra** | IaC that provisions all DataRobot resources | `infra/agent.py` — creates Custom Model + Deployment |
| **Agentic Playground** | DataRobot UI for testing deployed agents | Available after `dr run deploy` |

---

## 3. Integration Patterns with Neo4j

### Pattern A — Direct Neo4j tools inside the agent

The agent (LangGraph) is given Python functions as tools. Those tools call `neo4j-driver` directly. Neo4j credentials are passed as DataRobot **Runtime Parameters** (secure, stored in DataRobot vault, not in code).

```
User Prompt
    │
    ▼
DataRobot Agent (LangGraph)
    │  tool: query_company()
    │  tool: search_news_vector()
    │  tool: get_leadership()
    ▼
neo4j-driver → Neo4j AuraDB (Companies KG)
    │
    ▼
LLM Gateway (GPT-4o) → Synthesised report
```

**Best for:** Simple tool-use agents, full control over Cypher queries, no extra services needed.

---

### Pattern B — Neo4j via MCP server

A separate `neo4j-mcp-server` (Python pip) is deployed as its own DataRobot Custom Model. The agent connects to it over the MCP HTTP transport. This follows the same pattern as other integrations in this repo (e.g., `aws-agentcore/`, `vercel-agent/`).

```
DataRobot Agent (LangGraph)
    │  MCP client (HTTP)
    ▼
neo4j-mcp-server  ←── deployed as DataRobot Custom Model
    │                  endpoint: .../deployments/{id}/directAccess/mcp
    ▼
Neo4j AuraDB
```

**Best for:** Reusable tool layer, consistent with rest of repo's MCP-first approach, can be shared across multiple agents.

---

## 4. Key Technical Details

### Python SDK & packages

```bash
pip install datarobot[core]      # DataRobot platform SDK + agent workflow utils
pip install neo4j                # Neo4j driver
pip install langchain-neo4j      # LangChain Neo4j integration (optional)
pip install langgraph            # Agent orchestration (DataRobot default)
```

### Authentication

DataRobot agents use **Runtime Parameters** to securely inject secrets at deployment time — no secrets in code or Docker images:

```yaml
# model-metadata.yaml
runtimeParameterDefinitions:
  - fieldName: NEO4J_URI
    type: string
  - fieldName: NEO4J_USERNAME
    type: string
  - fieldName: NEO4J_PASSWORD
    type: credential
    credentialType: api_token
```

In `custom.py`:
```python
from datarobot_drum import RuntimeParameters
neo4j_uri = RuntimeParameters.get("NEO4J_URI")
neo4j_pass = RuntimeParameters.get("NEO4J_PASSWORD")["apiToken"]
```

### Agent entry point (`custom.py`)

DataRobot custom models expose a `chat` function following the OpenAI Chat Completions API shape:

```python
def chat(completion_create_params: dict, **kwargs):
    user_message = completion_create_params["messages"][-1]["content"]
    result = agent.invoke({"messages": [("human", user_message)]})
    # return streaming or non-streaming response
```

### Pulumi deployment (`infra/agent.py`)

```python
import pulumi_datarobot as dr

execution_env = dr.ExecutionEnvironment(
    "neo4j-agent-env",
    programming_language="python",
)

custom_model = dr.CustomModel(
    "neo4j-agent",
    base_environment_id=execution_env.id,
    files=["agent/custom.py", "agent/model-metadata.yaml"],
    runtime_parameter_values=[
        dr.CustomModelRuntimeParameterValueArgs(
            key="NEO4J_URI", type="string", value=neo4j_uri
        ),
    ],
)

deployment = dr.Deployment(
    "neo4j-agent-deployment",
    model_id=custom_model.id,
    label="Neo4j Industry Research Agent",
)
```

---

## 5. Proposed Folder Structure

```
datarobot/
├── README.md                        # Integration guide
├── datarobot_agent.ipynb            # Jupyter: setup + local run + deploy
├── requirements.txt                 # pip deps for notebook use
├── agent/
│   ├── custom.py                    # DR Custom Model entry point (chat handler)
│   ├── model-metadata.yaml          # Runtime params: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD
│   ├── agent.py                     # LangGraph agent definition + Neo4j tools
│   └── requirements.txt             # Agent deps: neo4j-driver, langgraph, datarobot[core]
├── mcp_server/
│   ├── custom.py                    # MCP server entry point (Pattern B)
│   └── model-metadata.yaml          # MCP server runtime params
└── infra/
    ├── __init__.py
    ├── agent.py                     # Pulumi: CustomModel + Deployment for agent
    └── mcp_server.py                # Pulumi: CustomModel + Deployment for MCP server
```

---

## 6. TO-DO List

### Phase 1 — Research & Setup (pre-implementation)

| # | Task | Owner | Notes |
|---|------|-------|-------|
| 1 | Obtain DataRobot account/sandbox | Client | Needed for `dr run deploy`; free trial at app.datarobot.com |
| 2 | Confirm supported LLM providers in client's DR instance | Client | Determines which model to use in LLM Gateway config |
| 3 | Decide agent framework | Team | Recommend **LangGraph** (DR default, most examples, aligns with existing `langgraph/` in repo) |
| 4 | Confirm Neo4j target | Team | AuraDB Free (demo DB) for Pattern A; separate writable instance for Pattern B MCP server |
| 5 | Install DataRobot CLI | Dev | `curl https://cli.datarobot.com/install \| sh` |

---

### Phase 2 — Pattern A: Direct Neo4j tools agent

| # | Task | Details |
|---|------|---------|
| A1 | Create `datarobot/` folder + `README.md` skeleton | Follow `INTEGRATION_TEMPLATE.md` |
| A2 | Write `agent/agent.py` — LangGraph agent with Neo4j tools | Tools: `query_company`, `search_news`, `get_leadership`, `vector_search` (mirrors `EXAMPLE_AGENT.md`) |
| A3 | Write `agent/custom.py` — DataRobot chat handler | Implements `def chat(completion_create_params, **kwargs)`, initialises LangGraph agent, handles streaming |
| A4 | Write `agent/model-metadata.yaml` | Define runtime params for `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`; set `ENABLE_LLM_GATEWAY_INFERENCE=true` |
| A5 | Write `agent/requirements.txt` | `neo4j-driver`, `langgraph`, `langchain-neo4j`, `datarobot[core]` |
| A6 | Test locally with `dr run agent:dev` | Verify tool calls hit Neo4j demo DB correctly |
| A7 | Write `infra/agent.py` Pulumi file | Provision Execution Environment → Custom Model → Deployment |
| A8 | Deploy and test with `dr run deploy` | Check Agentic Playground endpoint and `/chat/completions` REST call |

---

### Phase 3 — Pattern B: MCP server integration

| # | Task | Details |
|---|------|---------|
| B1 | Write `mcp_server/custom.py` | Wrap `neo4j-mcp-server` (pip) inside a DataRobot Custom Model; expose MCP HTTP endpoint |
| B2 | Write `mcp_server/model-metadata.yaml` | Runtime params: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` |
| B3 | Write `infra/mcp_server.py` Pulumi file | Deploy MCP server as separate DR Deployment; output `MCP_SERVER_ENDPOINT` |
| B4 | Update `agent/agent.py` for MCP variant | Use `langchain-mcp-adapters` or DR's built-in MCP client to connect to the deployed MCP endpoint |
| B5 | Test Pattern B end-to-end | Agent → DR MCP endpoint → neo4j-mcp-server → Neo4j AuraDB |

---

### Phase 4 — Notebook & Documentation

| # | Task | Details |
|---|------|---------|
| D1 | Write `datarobot_agent.ipynb` | Cells: install tools → `dr start` walkthrough → run locally → deploy → call endpoint → show results |
| D2 | Complete `README.md` | Sections: Overview, Architecture diagram (mermaid.ink), Patterns A+B, Auth (runtime params), Setup steps, Extension points |
| D3 | Add auth section | Document DataRobot Runtime Parameters as the auth mechanism (equivalent to AWS Secrets Manager / env vars in other integrations) |
| D4 | Add row to root `README.md` | Add `datarobot/` to the platform coverage table |
| D5 | PR review pass | Ensure consistent style with existing integrations (`langgraph/`, `aws-agentcore/`) |

---

## 7. Auth Mechanisms Summary

| Mechanism | Supported | Notes |
|-----------|-----------|-------|
| **DataRobot Runtime Parameters** | ✅ | Primary method — secrets injected at deployment time, stored in DR vault |
| **API Token (DataRobot)** | ✅ | For the DR SDK itself — `DATAROBOT_API_TOKEN` env var |
| **OAuth 2.0** | ✅ | For external service auth (Google, Box) via DR OAuth provider registry |
| **LLM Gateway** | ✅ | Handles LLM provider auth transparently; agent never sees raw API keys |
| **Hardcoded secrets** | ❌ | Never — use Runtime Parameters |

---

## 8. Reference Links

- [DataRobot Agent Application Template](https://github.com/datarobot-community/datarobot-agent-application) — the canonical starter
- [DataRobot Agent Templates (LangGraph, CrewAI, LlamaIndex)](https://github.com/datarobot-community/datarobot-agent-templates)
- [DataRobot MCP Template](https://github.com/datarobot-community/datarobot-mcp-template)
- [DataRobot Agentic AI Docs](https://docs.datarobot.com/en/docs/agentic-ai/agentic-develop/index.html)
- [DataRobot CLI](https://github.com/datarobot-oss/cli)
- [DataRobot Python SDK (PyPI)](https://pypi.org/project/datarobot/)
- [neo4j-mcp-server (pip)](https://pypi.org/project/neo4j-mcp/)
- [EXAMPLE_AGENT.md](../EXAMPLE_AGENT.md) — canonical Industry Research Agent spec
- [INTEGRATION_TEMPLATE.md](../INTEGRATION_TEMPLATE.md) — README template for all integrations
