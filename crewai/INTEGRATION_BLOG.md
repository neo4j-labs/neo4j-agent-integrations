# From Prompts to Proof: Building Grounded CrewAI Agents with Neo4j

## Introduction

This integration shows how to combine [CrewAI](https://www.crewai.com/), Neo4j,
the official Neo4j Model Context Protocol (MCP) server, and optional Neo4j
Agent Memory Server (NAMS) capabilities into a graph-grounded agent workflow.

The goal is not simply to give an LLM database credentials. The integration
creates a controlled tool boundary: CrewAI agents discover a graph schema,
execute read-oriented operations, pass verified findings through a sequential
workflow, and optionally retain durable context in NAMS.

Two delivery paths are included:

1. A self-contained, executed
   [`crewai_neo4j_walkthrough.ipynb`](notebooks/crewai_neo4j_walkthrough.ipynb)
   for learning, demonstrations, and repeatable experimentation.
2. Reusable modules in [`agent/`](agent/) for applications and scripts that
   need the same architecture as importable Python code.

Both use `gpt-5.4-mini` by default and have the same core principles:
schema-aware querying, read-only graph access, explicit memory behavior, and
evidence-based answers.

## The Problem: Why an Agent Needs More Than a Database Connection

A graph database is useful to an agent only when the agent can safely answer
three questions:

1. **What data is available?** Labels, relationship types, and properties vary
   between graphs. A Companies/News graph is not a NAMS graph.
2. **Which operation fits the question?** A company profile lookup, a
   relationship traversal, and a generic Cypher question require different
   tools and inputs.
3. **How should findings move through a workflow?** A researcher should gather
   evidence, an analyst should reason over the evidence, and a writer should
   distinguish facts from inferences.

CrewAI provides the orchestration primitives for this design. Neo4j provides
the connected data model. MCP provides a tool protocol and a local transport.
NAMS adds optional durable memory beyond the current run.

## Architecture at a Glance

![CrewAI, Neo4j, MCP, and NAMS architecture](https://raw.githubusercontent.com/neo4j-labs/neo4j-agent-integrations/main/crewai/assets/diagram-1.png)

The important routing decision is the MCP-first path. When
`MCP_SERVER_COMMAND` is configured, the reusable crew uses discovered MCP
tools instead of direct Neo4j driver tools. This is particularly useful for
Aura Graph Analytics environments where the standard driver's routing
discovery may not be available but the local MCP server can successfully query
the graph.

## CrewAI Concepts Mapped to the Integration

| CrewAI concept | Purpose here | Neo4j-facing behavior |
| --- | --- | --- |
| **LLM** | Interprets a request and selects tools. | Defaults to `gpt-5.4-mini`; answers must be grounded in tool results. |
| **Tool** | Gives an agent a bounded capability. | MCP tools, direct read-only tools, custom graph tools, and NAMS tools. |
| **Agent** | Handles one specialized responsibility. | Query agent answers one graph question; research, analysis, and writing agents build a briefing. |
| **Task** | Defines a required outcome for one agent. | Research facts, analyze relationships, or synthesize a Markdown brief. |
| **Crew** | Coordinates agents and tasks. | Runs tasks sequentially so later stages receive earlier evidence. |
| **Memory** | Preserves useful context beyond a single prompt. | Optional NAMS tools recall preferences and store verified findings. |

The design intentionally does not rely on an agent's prompt alone to keep
facts grounded. The available tools, their input schemas, and the sequential
task boundaries constrain how the workflow obtains and uses data.

## Local MCP: A Local Process, Not a Hosted Endpoint

The integration starts the official `neo4j-mcp-server` as a local stdio
subprocess. No hosted MCP URL and no OAuth client are required.

![Local MCP discovery and invocation sequence](https://raw.githubusercontent.com/neo4j-labs/neo4j-agent-integrations/main/crewai/assets/diagram-2.png)

[`agent/mcp.py`](agent/mcp.py) forwards the regular `NEO4J_*` settings to
their `NEO4J_MCP_*` equivalents when explicit MCP values are absent. It also
sets `NEO4J_MCP_READ_ONLY=true` and `NEO4J_TELEMETRY=false` by default.

At discovery time, the adapter reads each MCP tool's JSON schema and creates a
Pydantic input model dynamically. This matters for tools such as
`read-cypher`, where `query` is required: the agent receives a typed
requirement instead of a generic JSON blob and is less likely to invoke the
tool without the required argument.

### Why MCP-first routing matters

The integration uses this selection rule:

![MCP-first graph tool routing decision](https://raw.githubusercontent.com/neo4j-labs/neo4j-agent-integrations/main/crewai/assets/diagram-3.png)

This preserves a direct-driver fallback for environments that do not use MCP,
while preferring the transport that has been validated for the configured
local MCP workflow.

## Tooling Layers

The integration deliberately offers several tool layers because each is useful
for a different question.

### 1. Local MCP tools

The most generally useful tools are:

| Tool | Best use |
| --- | --- |
| `get-schema` | Understand labels, relationship types, and properties in an unfamiliar graph. |
| `read-cypher` | Run a targeted parameterized, read-oriented graph query. |

Start with `get-schema` when the graph model is unknown. It prevents a common
failure mode: asking a Companies/News question of a NAMS-oriented graph that
does not contain `Organization`, `Article`, or `IndustryCategory` nodes.

### 2. Direct Neo4j tools

[`agent/tools.py`](agent/tools.py) provides the direct-driver fallback:

| Tool | Purpose |
| --- | --- |
| `search_companies` | Search an organization name using the graph's expected Companies schema. |
| `query_company_profile` | Retrieve company metadata and related graph facts. |
| `analyze_company_relationships` | Traverse relationship paths, with bounded depth. |
| `run_cypher_query` | Run a constrained read-only Cypher operation. |
| `list_industry_categories` | Explore available industry taxonomy. |

These tools are useful when the database is a Companies/News graph and direct
Neo4j routing is supported. They are fallback tools when local MCP is not
configured.

### 3. Shared custom tools

[`agent/custom_tools.py`](agent/custom_tools.py) adapts the reusable
repository-level [`custom_tools/`](../custom_tools/) package for CrewAI. It
exposes company, relationship, industry, article, people, influence, and
investment operations.

The wrappers use a JSON `arguments` field because the shared functions have
different input shapes. The wrapper validates that the value is a JSON object,
then forwards it to the selected async function.

These tools are intentionally schema-specific. A response with no results can
be correct if the configured graph is a NAMS graph rather than the Companies
/ News graph they expect.

### 4. NAMS memory tools

NAMS is optional. When configured, [`agent/memory.py`](agent/memory.py) adds:

| Tool | Purpose |
| --- | --- |
| `search_memory` | Recall previously stored facts, entities, or prior context. |
| `save_memory_fact` | Persist a verified fact for future crews or sessions. |
| `get_preferences` | Retrieve stored reporting or analysis preferences. |

The key word is **verified**. Agents should save only graph-supported facts or
explicit user preferences, not speculative conclusions.

## Two Crew Patterns

### Natural-language graph query

`build_query_crew()` creates one graph intelligence agent. It receives NAMS
tools when available, local MCP tools when configured, otherwise direct Neo4j
tools, and the shared custom tools.

This is the right pattern for requests such as:

- “What labels and relationship types are available?”
- “Show all entities connected to DB and their relationship types.”
- “What organizations are within two hops of Acme, and how are they related?”
- “Which organizations has Acme invested in?”

The agent should call a tool before making factual claims and should state
when the graph lacks the requested entity or relationship.

### Multi-agent company briefing

`build_company_intelligence_crew()` creates a sequential three-agent crew.

![Sequential multi-agent company briefing flow](https://raw.githubusercontent.com/neo4j-labs/neo4j-agent-integrations/main/crewai/assets/diagram-4.png)

1. The **Lead Knowledge Graph Researcher** retrieves company facts and relevant
   graph structure.
2. The **Strategic Market & Graph Analyst** interprets bounded relationship
   paths, dependencies, and uncertainty.
3. The **Executive Intelligence Briefing Author** turns prior outputs into a
   Markdown briefing, clearly separating verified facts from implications.

This workflow is best for a company that exists in a Companies/News graph. For
a NAMS-oriented graph, use the query crew first to identify actual labels,
entities, and relationship patterns.

## The Self-contained Walkthrough Notebook

The notebook is not a thin launcher for the modules. It embeds its own
implementation of the MCP adapter, direct read-only tools, NAMS tools, and
CrewAI workflows. This gives readers one file they can inspect from setup to
output.

Its code cells include retained, sanitized outputs to show:

- dependency setup;
- configured model confirmation;
- tool registration;
- local MCP discovery and schema output;
- NAMS enabled or disabled behavior;
- a natural-language graph query; and
- a multi-agent briefing.

The notebook avoids persisting credentials. Its NAMS write demonstration is
explicitly opt-in: `SAVE_NAMS_DEMO` remains `False` until a user replaces the
sample with a verified fact and intentionally enables it.

## Configuration and Dependency Management

The reusable modules use [`uv`](https://docs.astral.sh/uv/) for reproducible
local dependency installation:

```bash
cd crewai
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e .
cp .env.example .env
```

The minimum configuration is:

```ini
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL_NAME=gpt-5.4-mini

NEO4J_URI=neo4j+s://<instance-id>.databases.neo4j.io
NEO4J_USERNAME=<database-username>
NEO4J_PASSWORD=<database-password>
NEO4J_DATABASE=<database-name>

MCP_SERVER_COMMAND=neo4j-mcp-server
NEO4J_MCP_READ_ONLY=true
NEO4J_TELEMETRY=false
```

To enable NAMS, add the service-specific values:

```ini
MEMORY_API_KEY=
MEMORY_WORKSPACE_ID=
```

The example configuration also disables optional outbound CrewAI tracing and
telemetry for local or corporate environments:

```ini
CREWAI_TRACING_ENABLED=false
CREWAI_DISABLE_TELEMETRY=true
```

If `uv` cannot validate a corporate certificate chain, retry dependency
installation with the operating system certificate store:

```bash
uv pip install --system-certs -r requirements.txt
```

## Security and Operational Boundaries

The design uses several layered controls:

![Layered security and operational boundaries](https://raw.githubusercontent.com/neo4j-labs/neo4j-agent-integrations/main/crewai/assets/diagram-5.png)

- **No credentials in source or notebook outputs.** Credentials stay in the
  environment or ignored `.env` file.
- **Read-oriented graph access.** The local MCP environment requests read-only
  operation; direct query helpers are designed for read-oriented Cypher.
- **Schema-first exploration.** The agent can inspect the actual graph before
  assuming labels or properties.
- **Typed MCP inputs.** Required arguments such as a Cypher `query` are
  visible to CrewAI.
- **Explicit memory writes.** NAMS stores durable information only through
  a dedicated save tool or explicit notebook opt-in.
- **Evidence before narrative.** Prompts direct agents to use tool results for
  factual statements and to identify missing data.

As with any tool-using agent, production deployments should apply least
privilege at the database level, review all exposed MCP capabilities, and
limit tools to those required for the intended workflow.

## Testing and Validation

The reusable modules have unit coverage for:

- crew and task construction;
- MCP configuration, tool discovery, typed schemas, and invocation;
- shared custom-tool adapters;
- NAMS memory helpers; and
- direct Neo4j tool behavior.

Run the suite with:

```bash
cd crewai
uv run pytest
uv run ruff check agent tests
```

The walkthrough notebook was also executed against the configured environment.
Its retained outputs demonstrate local MCP discovery and a live schema call
without exposing credentials. The notebook disables optional CrewAI telemetry
and prefers local MCP tools when configured, avoiding unnecessary telemetry
TLS noise and direct-driver routing problems in environments where MCP is the
validated connectivity path.

## Choosing the Right Starting Point

Use the **notebook** when you want a guided explanation, visible outputs, or a
single-file demonstration. Use the **reusable modules** when you need to
integrate the same tool-routing and crew construction into an application,
script, scheduled job, or another interface.

In both cases, start with schema discovery, use the graph's actual model
rather than assumed labels, and treat memory writes as a deliberate
knowledge-management operation. That combination turns an LLM from a
free-form text generator into a graph-aware workflow that can explain what it
knows, how it learned it, and where the graph does not yet provide evidence.

## Resources

- [CrewAI + Neo4j integration in this repository](https://github.com/neo4j-labs/neo4j-agent-integrations/tree/main/crewai)
- [Neo4j Agent Integrations repository](https://github.com/neo4j-labs/neo4j-agent-integrations)
- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Neo4j Agent Memory](https://neo4j.com/labs/agent-memory/)
- [CrewAI documentation](https://docs.crewai.com/)
- [Model Context Protocol specification](https://modelcontextprotocol.io/)
- [uv documentation](https://docs.astral.sh/uv/)
