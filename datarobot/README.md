# DataRobot + Neo4j Integration

## Overview

This integration packages a **Neo4j-backed research agent** for DataRobot in **three supported forms**:

| Path | Files | Deployment target | When to use |
|---|---|---|---|
| **A. DRUM custom model** (original) | `agent/custom.py`, `agent/agent.py`, `agent/mcp_client.py`, `agent/memory.py` | Registry → Workshop → Agentic Workflow custom model | Simple, dependency-light deployment; full control over the OpenAI tool-calling loop; works today with `infra/agent.py deploy` |
| **B. `datarobot-agent-application` template** (recommended by DataRobot) | `agent/myagent.py`, `agent/neo4j_tools.py` | `dr-genai` / `dr-agent` runtime via the [`datarobot-agent-application`](https://github.com/datarobot-community/datarobot-agent-application) template + `task deploy` | Aligns with DataRobot's native MCP server, LangGraph orchestration, governance/lineage tracking, and Agentic Memory Service |
| **C. Workload API** (DataRobot's published container-deployment API) | `agent/server.py`, `Dockerfile`, `infra/workload.py` | Container image → `POST /api/v2/workloads/` → managed autoscaled service | The platform-native deployment mechanism DataRobot is moving to as Custom Model support winds down; reuses Path A's `agent/custom.py::chat()` logic behind a plain HTTP server. See [Workload API docs](https://docs.datarobot.com/en/docs/api/dev-learning/workload-api/overview.html) |

Path A and Path B share the same Neo4j **companies** knowledge graph and can be extended with:

| Extension | Purpose | Config var(s) |
|---|---|---|
| **Neo4j Agent Memory (NAMS)** | Cross-session memory backed by a knowledge graph (Path A) | `MEMORY_API_KEY`, `MEMORY_WORKSPACE_ID` |
| **MCP (Model Context Protocol)** | Dynamically load tools from any MCP server (Path A) or DataRobot's global MCP server (Path B) | `MCP_SERVER_URL`, `MCP_AUTH_TOKEN` _(optional, Path A)_ |

> **Why three paths?** Path A was built first and is fully working today. After deploying it, DataRobot's team recommended aligning with their `datarobot-agent-application` template (native MCP server, `dr-genai`/`dr-agent` runtimes, governance lineage on `task deploy`) — that's Path B. DataRobot has since published the **Workload API** ([overview](https://docs.datarobot.com/en/docs/api/dev-learning/workload-api/overview.html)) as the platform's forward-looking, container-native deployment mechanism, replacing Custom Model deployment — that's Path C. Path C packages the exact same agent logic (`agent/custom.py::chat()`) as a container, deployed via `POST /api/v2/workloads/` instead of the Registry/Workshop custom-model flow. Path A remains functional for teams still on Custom Model deployment; Path C is the path to migrate to as that support winds down.

---

## Architecture (Path A — DRUM custom model)

```mermaid
flowchart TD
    User(["👤 User / DataRobot Playground / API Client"])

    subgraph DR["DataRobot Platform (DRUM)"]
        RP["RuntimeParameters\nOpenAI key · Neo4j creds\nMEMORY_API_KEY · MEMORY_WORKSPACE_ID\nMCP_SERVER_URL · MCP_AUTH_TOKEN"]
        ENTRY["custom.py\nload_model()  ·  chat()"]
    end

    subgraph Agent["Neo4j Research Agent  (agent.py)"]
        LOOP["OpenAI Tool-Calling Loop\ngpt-4o-mini / configurable"]
        BUILTIN["10 Built-in Neo4j Tools\nsearch_companies · query_company\nanalyze_relationships · search_news\npeople_at_company · list_industries · …"]
        MCPTOOLS["MCP Tools  (dynamic)\ndiscovered from MCP server at startup"]
    end

    subgraph MCP["MCP Layer  (mcp_client.py) — optional"]
        TRANSPORT["Transport auto-detect\nStreamable HTTP → SSE fallback\nstdio for local servers"]
        AUTH["Auth auto-detect\nBearer token  MCP_AUTH_TOKEN\nBasic  NEO4J_USERNAME:PASSWORD\nno-auth  open servers"]
        MCPSRV["MCP Server\nNeo4j MCP · NAMS MCP · custom"]
    end

    subgraph Memory["Neo4j Agent Memory  (memory.py) — optional"]
        WS["Workspace scoping\nMEMORY_WORKSPACE_ID → X-Workspace-Id"]
        STM["Short-Term Memory\nConversation history per session"]
        LTM["Long-Term Memory\nEntities · Knowledge Graph"]
    end

    subgraph Neo4j["Neo4j Graph DB"]
        KG["Organizations · People\nArticles · Industries"]
    end

    User -->|"POST /chat\n{messages:[…]}"| ENTRY
    RP -->|"inject secrets"| ENTRY

    ENTRY -->|"1 · get_context()\nsession_id + WORKSPACE_ID"| WS
    WS --> STM & LTM
    STM & LTM -->|"past context prepended\nas system message"| ENTRY

    ENTRY -->|"2 · agent.run()"| LOOP
    LOOP <-->|"Cypher queries"| BUILTIN <-->|"Bolt / neo4j+s"| KG
    LOOP <-->|"tool calls"| MCPTOOLS <-->|"anyio.run()"| TRANSPORT
    TRANSPORT <-->|"HTTP POST\nwith auth header"| AUTH --> MCPSRV

    LOOP -->|"final answer"| ENTRY
    ENTRY -->|"3 · save_turn()\nuser msg + response"| STM

    ENTRY -->|"OpenAI-format response\n{choices:[…], usage:{…}}"| User
```

---

## Files

```
datarobot/
├── .env.example
├── README.md
├── requirements.txt
├── run_local.py            ← local CLI test for Path A (mirrors DataRobot DRUM execution)
├── datarobot_agent.ipynb   ← Jupyter demo notebook (Path A)
├── Dockerfile               ← [Path C] linux/amd64 image for the Workload API container
├── agent/
│   ├── __init__.py
│   ├── agent.py            ← [Path A] Neo4jResearchAgent + 10 tools + MCP tool loader
│   ├── custom.py           ← [Path A] DataRobot load_model() + chat() with memory
│   ├── helpers.py          ← [Path A] prompt helpers + response formatting
│   ├── memory.py           ← [Path A] NAMS integration (graceful no-op if absent)
│   ├── mcp_client.py       ← [Path A] MCP client (graceful no-op if absent/unconfigured)
│   ├── model-metadata.yaml ← [Path A] DataRobot runtime parameter definitions
│   ├── myagent.py          ← [Path B] LangGraph agent for datarobot-agent-application template
│   ├── neo4j_tools.py      ← [Path B] LangChain-compatible Neo4j tools (7 tools)
│   ├── server.py            ← [Path C] FastAPI wrapper around custom.py::chat() for the Workload API
│   └── requirements.txt    ← deps bundled in DataRobot ZIP (all paths)
└── infra/
    ├── __init__.py
    ├── agent.py            ← [Path A] ZIP packager · DR API validator · automated deploy
    └── workload.py           ← [Path C] Workload API create/status/logs/delete CLI
```

---

## Quick Start (local)

```bash
cd datarobot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in OPENAI_API_KEY; optionally MEMORY_API_KEY, MEMORY_WORKSPACE_ID, MCP_SERVER_URL
python run_local.py "Give me a competitive snapshot of Google"
```

> **Troubleshooting: `neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information`**
> This means the driver connected but couldn't complete its routing-table handshake — common in
> GitHub Codespaces / devcontainers / restrictive corporate networks where the `ROUTE` bolt
> message is blocked/mangled even though a direct connection on port 7687 works fine. Fix by
> switching the URI scheme from routing (`neo4j+s://`) to direct (`bolt+s://`) in `.env`, which
> skips the routing-table fetch entirely:
> ```
> NEO4J_URI=bolt+s://demo.neo4jlabs.com:7687
> ```
> (The `401 Unauthorized` you may also see from `MCP list_tools failed (non-fatal): ...` in the
> same run is expected/harmless if `MCP_SERVER_URL`/`MCP_AUTH_TOKEN` aren't configured — MCP is
> optional and fails open.)

---

## Neo4j Agent Memory (NAMS)

```bash
# Get a free key at https://memory.neo4jlabs.com
# MEMORY_WORKSPACE_ID is the segment between the first two underscores in your key:
#   e.g. nams_<WORKSPACE_ID>_<secret>
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

> **`MEMORY_WORKSPACE_ID`** — required when using NAMS. Set it to the workspace ID portion of your key (`nams_<WORKSPACE_ID>_<secret>`). The SDK sends it as the `X-Workspace-Id` header to scope all memory to your workspace.

---

## MCP Integration

When `MCP_SERVER_URL` is set, the agent **discovers tools dynamically** from the MCP server at startup and makes them available to the LLM alongside the built-in Neo4j tools.

```bash
# Neo4j MCP official server (uses NEO4J_USERNAME/PASSWORD for Basic auth automatically)
MCP_SERVER_URL=https://neo4j-mcp-official-1008050579172.us-central1.run.app/mcp \
  python run_local.py "What schema does my Neo4j database have?"

# NAMS MCP server (16 memory tools — run locally)
uvx "neo4j-agent-memory[mcp]" mcp serve --password <neo4j-password> &
MCP_SERVER_URL=http://localhost:8080/sse python run_local.py "What do you know about me?"

# Any HTTP MCP server with Bearer token auth
MCP_AUTH_TOKEN=my-bearer-token \
MCP_SERVER_URL=https://my-mcp-server.example.com/mcp \
  python run_local.py "..."

# stdio MCP server
MCP_SERVER_URL="uvx my-mcp-server serve" python run_local.py "..."
```

**Supported transports** (auto-detected):
- **Streamable HTTP** (`http://` or `https://`) — tried first (modern MCP servers)
- **SSE** — fallback for `http://` or `https://` servers that don't support streamable HTTP
- **stdio** — any other string treated as a shell command

**Authentication** (auto-detected from env vars):
| Priority | Condition | Header sent |
|---|---|---|
| 1 | `MCP_AUTH_TOKEN` is set | `Authorization: Bearer <token>` |
| 2 | `NEO4J_USERNAME` + `NEO4J_PASSWORD` are set | `Authorization: Basic <b64(user:pass)>` |
| 3 | Neither | No auth header (open servers) |

> The neo4j-mcp-official server uses Neo4j Basic auth — no extra config needed, it reuses the existing `NEO4J_USERNAME`/`NEO4J_PASSWORD`.

MCP is **non-blocking** — if `MCP_SERVER_URL` is absent or the `mcp` package is not installed, the agent runs with its 10 built-in tools only.

> **Seeing `MCP list_tools failed (non-fatal): ... 401 Unauthorized` followed by
> `neo4j.exceptions.ServiceUnavailable: Unable to retrieve routing information`?**
> These are two unrelated issues that often show up together while testing MCP:
> - The `401` on `list_tools` is expected/harmless if your MCP server requires auth you
>   haven't configured yet (see the auth table above) — MCP fails open, so it doesn't stop
>   the agent.
> - The `ServiceUnavailable` is the real failure — it's a **Neo4j driver routing** problem,
>   not MCP-related, common in Codespaces/devcontainers. See the troubleshooting note under
>   [Quick Start](#quick-start-local) — switch `NEO4J_URI` from `neo4j+s://` to `bolt+s://`.
>
> **Seeing `MCP list_tools failed (non-fatal): ... 405 Method Not Allowed`?** This means
> Streamable HTTP failed silently and the client fell back to the older SSE transport, which
> `neo4j-mcp-official`'s `/mcp` endpoint (POST-only) rejects. The most common cause is an
> outdated `mcp` package — `streamable_http_client`'s current `http_client=` argument requires
> `mcp>=1.24.0` (already pinned in `requirements.txt`); run `pip install -U -r requirements.txt`
> to pick it up. As of this fix, the underlying Streamable HTTP failure is also now logged at
> `WARNING` level (not just `DEBUG`) so the real cause is visible instead of only seeing the
> downstream SSE 405.

---

## Path B — `datarobot-agent-application` template (`myagent.py`)

`agent/myagent.py` + `agent/neo4j_tools.py` implement the pattern DataRobot's team recommended after reviewing Path A:

```mermaid
flowchart TD
    User(["👤 User / DR Playground / dr-agent runtime"])

    subgraph Template["datarobot-agent-application template"]
        NAT["dr-genai / dr-agent runtime
custompy_adaptor() entry point"]
        MCPCTX["mcp_tools_context()
DataRobot global MCP server
(native — no custom transport code)"]
    end

    subgraph MyAgent["myagent.py — LangGraph workflow"]
        PLANNER["planner_node
binds Neo4j + MCP tools to the LLM
native tool_calls loop (max 4 rounds)"]
        RELAY["relay
AIMessage → HumanMessage"]
        WRITER["writer_node
formats final Markdown report"]
    end

    subgraph Neo4jTools["neo4j_tools.py — 7 LangChain tools"]
        CYPHER["run_cypher_query · search_companies
query_company_profile · list_industries
companies_in_industry
analyze_company_relationships
people_at_company"]
    end

    subgraph Neo4j["Neo4j Graph DB"]
        KG["Organizations · People
Articles · Industries"]
    end

    User -->|"RunAgentInput"| NAT
    NAT -->|"forwarded_headers +
authorization_context"| MCPCTX
    NAT -->|"agent.invoke()"| PLANNER
    MCPCTX -->|"native MCP tools
(if configured on DR platform)"| PLANNER
    PLANNER <-->|"tool_calls"| CYPHER <-->|"Bolt / neo4j+s"| KG
    PLANNER --> RELAY --> WRITER
    WRITER -->|"DRAgentEventResponse"| NAT --> User
```

**Key differences from Path A:**

| Aspect | Path A (`agent.py`/`custom.py`) | Path B (`myagent.py`/`neo4j_tools.py`) |
|---|---|---|
| Orchestration | Manual OpenAI tool-calling loop | LangGraph `StateGraph` (planner → writer) |
| MCP | Custom `mcp_client.py` (transport/auth auto-detect) | DataRobot's native global MCP server via `mcp_tools_context()` |
| Memory | NAMS (`memory.py`) | DataRobot's native Agentic Memory Service (integrate via `datarobot_genai`) |
| Deployment | `infra/agent.py deploy` → Workshop custom model | `dr start` / `dr run dev` / `task deploy` with the template |
| Governance | None built-in | Lineage, versioning via `task deploy` |
| Dependencies | `openai`, `neo4j`, `mcp` (optional) | `datarobot_genai`, `langgraph`, `langchain-neo4j` |

**Using Path B:**

1. Clone [`datarobot-community/datarobot-agent-application`](https://github.com/datarobot-community/datarobot-agent-application) and run `dr start` to scaffold the template (LangGraph agent choice).
2. Copy `agent/myagent.py` and `agent/neo4j_tools.py` from this repo into the template's `agent/agent/` directory.
3. Set `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` in the template's `.env`.
4. Run `dr run dev` locally, or `task deploy` to publish with full governance/lineage tracking.
5. If `datarobot_genai` is not installed (e.g. running `myagent.py` standalone), the module degrades gracefully: `graph_factory()` and the Neo4j tools still work with any LangChain-compatible LLM, but the DataRobot-specific `MyAgent`/`custompy_adaptor` entry points are skipped.

> **Tested:** `graph_factory()` was verified end-to-end locally with `ChatOpenAI` + live Neo4j (`neo4j+s://demo.neo4jlabs.com`) — the planner correctly binds and calls `neo4j_tools` via native LangChain tool-calling, and the writer produces a formatted Markdown report.

---

## Path C — Workload API (`agent/server.py`, `Dockerfile`, `infra/workload.py`)

DataRobot has published the **Workload API** — a REST API for running arbitrary container images as managed, autoscalable services — as the platform's forward-looking deployment mechanism, replacing Custom Model deployment (Path A). See [Workload API overview](https://docs.datarobot.com/en/docs/api/dev-learning/workload-api/overview.html).

```mermaid
flowchart LR
    User(["👤 User / client app"]) -->|"POST /v1/chat/completions"| Server

    subgraph Container["Container (linux/amd64)"]
        Server["agent/server.py
FastAPI: /healthz · /readyz
/v1/chat/completions"]
        Custom["agent/custom.py::chat()
same logic as Path A"]
        Server --> Custom
    end

    subgraph Neo4j["Neo4j Graph DB"]
        KG["companies knowledge graph"]
    end

    Custom -->|"Bolt / neo4j+s"| KG

    subgraph DR["DataRobot Workload API"]
        Workload["POST /api/v2/workloads/
readiness/liveness probes
autoscaling · rolling replacement"]
    end

    Workload -->|"routes traffic to"| Server
```

`agent/server.py` is a thin FastAPI wrapper that calls the **exact same** `agent/custom.py::chat()` used by Path A, so behavior (memory, MCP, Neo4j tools) is identical — only the transport changes from DRUM's in-process `chat()` convention to plain HTTP.

**Deploying:**

```bash
# 1. Build and push a linux/amd64 image (required — ARM64-only images crash-loop on the platform)
docker buildx build --platform linux/amd64 -t <registry>/<org>/neo4j-datarobot-agent:latest --push .

# 2. Deploy via the Workload API (polls until the workload reaches "running")
python infra/workload.py create --image <registry>/<org>/neo4j-datarobot-agent:latest

# 3. Check status / logs, or tear down
python infra/workload.py status <workload_id>
python infra/workload.py logs <workload_id>
python infra/workload.py delete <workload_id>
```

Secrets (`OPENAI_API_KEY`, `NEO4J_PASSWORD`, `MEMORY_API_KEY`, `MCP_AUTH_TOKEN`) should be injected via DataRobot credentials rather than plaintext env vars:

```bash
python infra/workload.py create --image <image> \
  --credential OPENAI_API_KEY=<dr_credential_id>:apiToken \
  --credential NEO4J_PASSWORD=<dr_credential_id>:password
```

If no `--credential` mapping is given for a secret, `infra/workload.py` falls back to reading it as a plaintext env var from the local `.env` (convenient for local/demo deployments, not recommended for production).

> **Tested:** `agent/server.py` was run locally with `uvicorn`, and `/healthz`, `/readyz`, and `/v1/chat/completions` were all verified against the live Neo4j `companies` database and a real OpenAI call — confirmed a 200 response with a correct tool-calling answer. The actual `POST /api/v2/workloads/` deployment call in `infra/workload.py` follows DataRobot's documented Workload API contract but has not been run against a live DataRobot Workload API endpoint (requires DataRobot platform access with the Workload API enabled for the org); the container/server logic it deploys has been fully tested.

---

## Built-in Neo4j tools (Path A — `agent.py`)

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

## Neo4j LangChain tools (Path B — `neo4j_tools.py`)

| Tool | Description |
|---|---|
| `run_cypher_query` | Execute any raw Cypher query |
| `search_companies` | Full-text company lookup |
| `query_company_profile` | Company profile — summary, industries, locations, leadership |
| `list_industries` | List all industry categories |
| `companies_in_industry` | Companies in a specific industry |
| `analyze_company_relationships` | Org-to-org graph traversal (depth 1–4) |
| `people_at_company` | Executives and board members |

---

## Notebook

`datarobot_agent.ipynb` is a **7-section end-to-end demo notebook**:

| Section | What it covers |
|---|---|
| **1. Setup** | Install deps, credential check, DataRobot access indicator |
| **2. Local smoke test** | Call `chat()` in-process — no DR deployment needed |
| **3. Deploy** | Run `infra/agent.py deploy` inline to push to DataRobot |
| **4. Live endpoint test** | Call the deployed Chat completion API |
| **5. Multi-turn memory** | Two-turn conversation showing NAMS context recall |
| **6. MCP tools** | Question that triggers MCP + built-in Neo4j tools together |
| **7. Batch queries** | 4 research questions run end-to-end against the deployment |

Run it locally with `jupyter notebook datarobot_agent.ipynb`, or upload it directly to **DataRobot Notebooks** after deployment to use it there.

> Set `DR_DEPLOYMENT_ID` in `.env` before running sections 4–7 (copy the ID from the deploy output or the DataRobot Deployments UI).

---

## DataRobot packaging & deployment

### Option A — Fully automated (recommended)

Set the required variables in `.env` (copy from `.env.example`) then run:

```bash
python infra/agent.py deploy
```

This single command:
1. Packages all agent files into `dist/neo4j_datarobot_agent.zip`
2. Authenticates with your DataRobot instance
3. Creates a custom model with `targetType: agenticWorkflow`
4. Uploads all files using the Python 3 drop-in environment
5. Waits for the container build to succeed
6. Registers the version in the Model Registry
7. Creates a deployment and prints the Chat completion endpoint URL

After deployment, open it in the DataRobot UI and set the **Runtime Parameters** (credentials must be set via the UI — see table below).

```bash
# Dry-run: package + validate only, no API mutations
python infra/agent.py deploy --dry-run

# Package to ZIP only (for manual upload)
python infra/agent.py package

# Validate DataRobot API credentials only
python infra/agent.py validate
```

Required `.env` variables for automated deploy:

```
DATAROBOT_ENDPOINT=https://app.datarobot.com
DATAROBOT_API_TOKEN=your-token-here
DR_MODEL_NAME=Neo4j DataRobot Agent   # optional, this is the default
```

---

### Option B — Manual upload

```bash
python infra/agent.py package
# → dist/neo4j_datarobot_agent.zip
```

Then in the DataRobot UI:

1. Click **Registry** in the top nav → **Workshop** in the **left sidebar**
   > ⚠️ Workshop is a **left sidebar item** — not the Data/AI Catalog section. Look for it below "Models" in the left nav.
2. Click the **Agentic workflows** tab → **+ Add a workflow**
3. Enter a **Model name**, confirm **Target type = Agentic Workflow**, click **Add model**
4. **Assemble** tab → **Files** section → **+ Add files** → upload all files from `dist/neo4j_datarobot_agent.zip`
5. **Assemble** tab → **Runtime parameters** → add each key from the table below
6. _(Optional)_ Click **Test workflow** to verify the agent responds
7. Click **Register a workflow** → fill in a name → **Register a workflow**
8. Go to **Registry** → **Models** → find your workflow → click **Deploy**

---

## Runtime parameters

| Parameter | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | _(required)_ |
| `OPENAI_MODEL` | Chat model | `gpt-4o-mini` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `OPENAI_BASE_URL` | _(optional)_ Override OpenAI base URL — point to DataRobot's LLM proxy, Azure OpenAI, or any OpenAI-compatible endpoint | _(optional, blank = OpenAI)_ |
| `NEO4J_URI` | Neo4j connection string | `neo4j+s://demo.neo4jlabs.com:7687` |
| `NEO4J_USERNAME` | Neo4j username | `companies` |
| `NEO4J_PASSWORD` | Neo4j password | _(required)_ |
| `NEO4J_DATABASE` | Neo4j database | `companies` |
| `AGENT_MAX_TOOL_STEPS` | Max tool-call iterations | `6` |
| `MEMORY_API_KEY` | NAMS key — leave blank to disable memory | _(optional)_ |
| `MEMORY_WORKSPACE_ID` | NAMS workspace ID — the segment between the first two underscores in your key: `nams_<WORKSPACE_ID>_...` | _(optional)_ |
| `MCP_SERVER_URL` | MCP server URL — leave blank to skip MCP | _(optional)_ |
| `MCP_AUTH_TOKEN` | Bearer token for MCP servers requiring token auth (Basic auth uses `NEO4J_USERNAME`/`NEO4J_PASSWORD` automatically) | _(optional)_ |

**Notebook-only variable** (set in `.env`, not a DR runtime parameter):

| Variable | Purpose |
|---|---|
| `DR_DEPLOYMENT_ID` | Deployment ID for the notebook's live endpoint test (sections 4–7) |

---

## Notes

- Secrets are loaded from DataRobot runtime parameters first; `.env` is for local development only.
- `neo4j-agent-memory` and `mcp` both require Python ≥ 3.10. DataRobot's runtime satisfies this. On Python 3.9 locally, both features silently disable themselves.
- `infra/agent.py validate` requires direct access to `app.datarobot.com`. Corporate proxies (Zscaler) return HTTP 403 — run from a network-open machine.
- `myagent.py` (Path B) works on Python 3.9+ since it only depends on `langchain-core`/`langgraph`/`langchain-neo4j`; `datarobot_genai` itself requires the DataRobot template environment and is optional for local testing.
- Path B was verified end-to-end locally: `graph_factory()` compiled as a LangGraph `StateGraph`, invoked with `ChatOpenAI`, and confirmed to call `neo4j_tools` via native tool-calling against the live `neo4j+s://demo.neo4jlabs.com` companies database.
- Path C (`agent/server.py`) was verified end-to-end locally via `uvicorn` — `/healthz`, `/readyz`, and `/v1/chat/completions` all confirmed working against the live Neo4j database and a real OpenAI call. `infra/workload.py`'s actual `POST /api/v2/workloads/` call has not been exercised against a live DataRobot org (requires Workload API access), but follows DataRobot's published request/response contract.
