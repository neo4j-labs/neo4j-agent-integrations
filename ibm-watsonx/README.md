# IBM watsonx Orchestrate + Neo4j Integration

Build a watsonx Orchestrate agent that uses a Neo4j knowledge graph as its knowledge layer, through the Model Context Protocol (MCP).

The agent inspects the graph schema, generates Cypher, and answers questions about companies, people, and investments. Graph access comes from the official `mcp-neo4j-cypher` server, registered as a **local (stdio) toolkit** that Orchestrate installs and runs inside its own runtime.

---

## Background

**IBM watsonx Orchestrate** is IBM's platform for building and running AI agents. Unlike a code-first framework where the agent lives in your own process, an Orchestrate agent lives on the platform: you describe it declaratively — a model, a style, instructions, and a toolset — and Orchestrate runs it, gives it a chat surface, and manages its lifecycle across draft and live environments. It is framework-agnostic at the edges (external agents built on LangGraph, CrewAI, or BeeAI can be registered as collaborators over A2A), but the agent you build here is a **native** Orchestrate agent defined in YAML.

**Neo4j** is a graph database. Instead of rows and joins, it stores entities as nodes and relationships as first-class connections between them, which makes multi-hop questions — "which people sit on the boards of two different companies," "what connects these two organizations" — cheap to express and fast to answer. That property is exactly what makes a graph a strong knowledge layer for an agent: the hard questions for a normal database are the natural ones for a graph.

**The Model Context Protocol (MCP)** is the open standard that connects the two. An MCP server exposes a set of tools over a common interface; an MCP client — here, watsonx Orchestrate — discovers those tools and lets the agent call them. Neo4j publishes an official MCP server, `mcp-neo4j-cypher`, that exposes graph operations as tools: read the schema, run read-only Cypher, and (not used here) run write Cypher. Because the contract is standardized, the same server that works in Claude Desktop or VS Code works in Orchestrate with no changes.

**How the pieces fit.** Orchestrate can consume an MCP server in two ways: a **remote** server reached over HTTPS that you host yourself, or a **local (stdio)** server that Orchestrate installs and runs inside its own runtime. This integration uses the local option, because it removes hosting entirely — no container, no deployment, no public endpoint, no inbound authentication layer. Orchestrate installs `mcp-neo4j-cypher`, runs it as a subprocess, and passes the Neo4j credentials into that process as environment variables. The server then connects outbound to Neo4j over Bolt. Note that Orchestrate's own built-in knowledge feature is vector-based RAG (backed by stores such as Milvus or Elasticsearch); there is no native graph retriever, so graph access is provided through MCP tools rather than a knowledge base.

---

## Architecture

![IBM Watsonx orchestrate + Neo4j MCP Integration](ibm_neo4j_architecture.png.png)

The runtime execution flow functions along the following boundaries:

**Agent Runtime.** The user prompt is received by the Orchestrate-hosted chat surface and passed to the native agent `neo4j_explorer` (model `bedrock/openai.gpt-oss-120b-1:0`). The agent's instructions govern tool selection, schema-first querying, and result limits.

**Tool Resolution.** The agent's toolset resolves to the imported toolkit `neo4j_local_mcp` and the Python tool `get_investments`. Orchestrate performs tool discovery and schema validation at import time using the **draft** credentials, and executes tools at runtime using the **live** credentials.

**MCP Execution.** Orchestrate installs the `mcp-neo4j-cypher` package and runs it as a local stdio process within its own runtime. The `neo4j_local_creds` connection is injected into that process as environment variables (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `NEO4J_READ_ONLY`). No inbound network exposure or HTTP authentication layer is involved.

**Graph Execution.** The MCP server connects outbound to Neo4j over Bolt (`neo4j+s://`) and executes `get-schema` or `read-cypher` against the companies knowledge graph, returning structured results to the agent for synthesis. `NEO4J_READ_ONLY=true` prevents write operations at the server level.

The connection is the only place credentials live — the MCP server reads them as environment variables, the Python tool reads them through the connections API.

---

## Prerequisites

- watsonx Orchestrate instance (the free trial is sufficient)
- Python 3.11+, macOS or Linux (use WSL2 on Windows)
- Network access to a Neo4j instance

The defaults target the public Neo4j **companies** demo database, so no database setup is required. Point the `NEO4J_*` values at an Aura or self-managed instance to use your own graph — nothing else in the setup changes.

---

## Quickstart

```bash
cd ibm-watsonx-orchestrate
python3.11 -m venv venv && source venv/bin/activate
pip install ibm-watsonx-orchestrate

cp example.env .env      # then fill in WO_INSTANCE_URL
make all
```

`make all` registers the environment, creates the connection, adds the MCP toolkit, and imports the Python tool. It will prompt once for your API key.

Then create the agent in the console — about five minutes, following [`docs/console-agent-setup.md`](docs/console-agent-setup.md). Agent creation is the one step the CLI cannot currently do; see [`docs/known-issues.md`](docs/known-issues.md#1-cli-import-of-a-native-agent-with-a-toolkit-fails).

### Getting your credentials

In the Orchestrate console, click your profile icon and go to **Settings → API details**. Copy the **service instance URL** into `WO_INSTANCE_URL`, then click **Generate API key** — it is shown once. Use the key from this page, not an IBM Cloud IAM key (an IAM key produces a misleading `Scope not found` error).

---

## What each step does

| Target | Command | Effect |
|---|---|---|
| `make env` | `orchestrate env add` | Registers and activates the instance |
| `make connections` | `orchestrate connections …` | Creates `neo4j_local_creds` (`key_value`) for draft and live |
| `make mcp-toolkit` | `orchestrate toolkits add --kind mcp` | Installs and registers `mcp-neo4j-cypher` as a local stdio server |
| `make custom-tool` | `orchestrate tools import -k python` | Imports `get_investments` with its pinned dependencies |
| `make agent` | `orchestrate agents import` | Blocked in ADK 2.12.0 — create the agent in the console instead |
| `make verify` | — | Lists toolkits, tools, models, and agents |

Individual scripts live in [`scripts/`](scripts/) if you would rather run the commands one at a time.

---

## Layout

```
.
├── Makefile                      one target per setup step
├── .env.example                  configuration template
├── agents/
│   └── neo4j_explorer.yaml       canonical agent definition
├── tools/
│   ├── get_investments.py        curated Python tool
│   └── requirements.txt          exact-pinned dependencies
├── scripts/                      01_env … 05_agent
├── memory-agent/                 LangGraph memory + graph agent
│   ├── agent.py                  recall → agent(+tools) → persist graph
│   ├── agent.yaml                agent package definition
│   ├── requirements.txt
│   └── setup.sh                  connections + import + connect
└── docs/
    ├── console-agent-setup.md    the one manual step
    ├── known-issues.md           errors and their causes
    └── images/                   console screenshots
```

---

## Notes on the custom tool

`get_investments` is deliberately minimal — one query, one clear docstring. Two things about it are worth copying into your own tools:

**Dependencies are installed server-side and must be pinned exactly.** `neo4j==5.28.1`, never `neo4j>=5`. Packages are also checked against a tenant-specific allowlist at import time. The first call after import may return *"We are configuring your tool in the background"* — that is the install running; wait a few minutes and retry.

**The docstring is the routing signal.** Orchestrate derives the tool description and argument descriptions from a Google-style docstring, and the model chooses tools from those descriptions. A vague docstring means the agent falls back to `read-cypher` and your curated query never runs.

---

## Memory + graph (cross-session, LangGraph)

The `memory-agent/` folder contains a second, independent agent that adds two
capabilities a native YAML agent cannot: **long-term memory** and **LLM-routed
graph queries**, in one code-based agent. It is a **LangGraph agent imported
into Orchestrate** (running inside the platform runtime) that uses Neo4j as
*both* layers — the **Neo4j Agent Memory Service (NAMS)** for what it remembers,
and the companies graph for what it knows.

### How it works

```
recall  → read relevant facts from the NAMS entity graph
agent   → LLM answers, optionally emitting graph tool calls
   │ tools_condition
   ├─ (tool calls) → tools → agent      loop until the LLM is done
   └─ (no calls)   → persist → END
```

Memory is recalled every turn (cheap, workspace-scoped) and injected into the
prompt. The **companies graph is queried only when the LLM decides it is
needed** — the graph is exposed as two tools (`get_graph_schema`,
`run_graph_query`) bound to the model, and `tools_condition` routes to them
only when the model emits a tool call. A question answerable from memory alone
runs no graph query; a company question does; a question needing both pulls the
preference from memory and filters the graph query accordingly.

Memory lives in NAMS rather than the agent's own state, which matters because
imported LangGraph agents only persist messages between turns, not custom
state. Because memory is external and workspace-scoped, it carries across
separate chat sessions.

### Setup

Two connections supply credentials (Orchestrate injects them as
`{app_id}_{credential_type}`); the companies graph uses the public Neo4j demo
database and needs no connection.

| Connection | Injected key | Value |
|---|---|---|
| `nams_api` | `nams_api_api_key` | NAMS API key (memory.neo4jlabs.com/dashboard) |
| `nams_workspace` | `nams_workspace_api_key` | NAMS workspace id (`X-Workspace-Id`) |
| `llm_openai` | `llm_openai_api_key` | OpenAI API key for the agent's LLM |

```bash
cd memory-agent
export NAMS_API_KEY=...
export NAMS_WORKSPACE_ID=...
export OPENAI_API_KEY=...
./setup.sh
```

`setup.sh` creates the connections, imports the agent with
`orchestrate agents import --package-root .`, and attaches the connections with
`orchestrate agents connect`. Unlike the Phase 1 agent, this one imports fully
from the CLI — the toolkit limitation does not apply to imported LangGraph
agents.

### Demonstrating it

Memory works **across sessions**, so use two separate chats:

1. **Session A** — state a fact: *"Remember that John is working on opportunities in cyber security domain."* The agent acknowledges it.
2. **Wait.** NAMS extracts entities asynchronously — a few seconds to a few minutes. You can watch entities appear in the NAMS dashboard.
3. **Session B** (new chat) — ask: *"What companies should I look at?"* The agent recalls the fintech preference and queries the companies graph filtered to fintech — memory and graph together.

### A note on consistency

Writes are acknowledged immediately, but entity extraction runs in the
background, so memory is **eventually consistent** — a fact is not always
retrievable in the same turn it was stated. This is a characteristic of the
NAMS extraction pipeline, not of watsonx Orchestrate or the agent. The
cross-session demo is unaffected, since time passes between sessions.

---

## Verified against

watsonx Orchestrate trial (AWS `ap-south-1`) · ADK 2.12.0 · Python 3.11 · `mcp-neo4j-cypher` (local stdio) · Neo4j companies demo database · `bedrock/openai.gpt-oss-120b-1:0`

---

## Resources

**watsonx Orchestrate**
- Product: https://www.ibm.com/products/watsonx-orchestrate
- Documentation: https://www.ibm.com/docs/en/watsonx/watson-orchestrate
- ADK developer docs: https://developer.watson-orchestrate.ibm.com
- ADK repository: https://github.com/IBM/ibm-watsonx-orchestrate-adk

**Neo4j**
- Neo4j MCP servers: https://github.com/neo4j-contrib/mcp-neo4j
- mcp-neo4j-cypher on PyPI: https://pypi.org/project/mcp-neo4j-cypher
- Neo4j Aura (managed Neo4j): https://neo4j.com/product/auradb

**Model Context Protocol**
- Specification: https://modelcontextprotocol.io
