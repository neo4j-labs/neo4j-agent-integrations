# OpenAI Agents SDK + Neo4j Integration

This folder demonstrates three approaches for integrating **Neo4j** with the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/). Each approach builds on the previous one, adding more capability.

| Notebook | Description |
|----------|-------------|
| [openai_agents.ipynb](openai_agents.ipynb) | End-to-end walkthrough of all three approaches with working examples |

## Overview

The demo uses the publicly accessible **Neo4j companies knowledge graph** — `Organization` nodes linked to `Article` nodes via `[:MENTIONS]` relationships.

## Prerequisites

- Python 3.10+
- An OpenAI API key
- A running Neo4j instance (the notebook uses the public read-only `companies` demo database)

## Installation

```bash
pip install --upgrade openai-agents "neo4j-agent-memory[openai-agents]"
pip install --ignore-requires-python neo4j-mcp-server
```

## Configuration

Set the following environment variables before running the notebook:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Neo4j Knowledge Graph (public read-only demo — no changes needed)
export NEO4J_URI="neo4j+s://demo.neo4jlabs.com:7687"
export NEO4J_USERNAME="companies"
export NEO4J_PASSWORD="companies"
export NEO4J_DATABASE="companies"

# MCP server port
export MCP_PORT="8443"

# Neo4j Memory DB — only required for Approach 3 (must be writable)
export MEMORY_NEO4J_URI="neo4j+s://your-instance.databases.neo4j.io"
export MEMORY_NEO4J_USERNAME="neo4j"
export MEMORY_NEO4J_PASSWORD="your-password"
export MEMORY_NEO4J_DATABASE="neo4j"
```

> **Security:** Never hardcode credentials in notebook cells or commit them to source control. Use environment variables or a secrets manager.

---

## Approach 1 — MCP Agent

Connect an OpenAI agent to Neo4j via the [Model Context Protocol](https://openai.github.io/openai-agents-python/mcp/). The agent automatically decides which MCP tools to call (`get-schema`, `read-cypher`, etc.) to answer natural-language questions.

**Key APIs:** `MCPServerStreamableHttp`, `Agent`, `Runner`

```python
from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp

mcp_server = MCPServerStreamableHttp(
    params={
        "url":     f"http://localhost:{MCP_PORT}/mcp",
        "headers": {"Authorization": f"Basic {creds}"},
    },
    name="neo4j",
)
await mcp_server.connect()

agent = Agent(
    name="neo4j_explorer",
    instructions="You are a graph database assistant ...",
    mcp_servers=[mcp_server],
    model="gpt-5.4",
)

result = await Runner.run(agent, "How many organizations are in the database?")
print(result.final_output)
```

**Example output:**

```
Query: How many organizations are in the database?

Result: There are 46,088 organizations in the database.
```

**When to use:** You want a fully autonomous agent that can explore and query any Neo4j graph without writing Cypher yourself.

---

## Approach 2 — Custom Tools Agent

Extend the MCP agent with hand-written Cypher-backed tools using the `@function_tool` decorator. Custom tools and MCP tools are passed to the same agent — the framework routes each call to the correct handler.

**Key APIs:** `@function_tool`, `Agent(tools=[...], mcp_servers=[...])`

```python
from agents import Agent, Runner, function_tool
import neo4j as _neo4j

driver = _neo4j.AsyncGraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
)

@function_tool
async def get_investments(company: str) -> list:
    """Returns investments made by a company — ids, names, and types."""
    result = await driver.execute_query(
        """MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
           WHERE o.name = $company
           RETURN i.id AS id, i.name AS name, head(labels(i)) AS type""",
        company=company,
        database_=os.environ["NEO4J_DATABASE"],
    )
    return [record.data() for record in result.records]

agent = Agent(
    name="neo4j_custom",
    instructions="You are a helpful assistant with access to a Neo4j graph database ...",
    tools=[get_investments],
    mcp_servers=[mcp_server],
    model="gpt-5.4",
)

result = await Runner.run(agent, "Which companies did Google invest in?")
print(result.final_output)
```

**Example output:**

```
Query: Which companies did Google invest in?

Result: Google has invested in the following companies:

1. Ionic Security
2. Avere Systems
3. FlexiDAO
4. Cloudflare
5. Trifacta
```

**When to use:** You need precise control over specific queries (e.g., complex multi-hop Cypher) while still leveraging the MCP server for general graph exploration.

---

## Approach 3 — Memory Agent

Add cross-session persistent memory to the agent using [`neo4j-agent-memory`](https://pypi.org/project/neo4j-agent-memory/). The agent stores conversation history and entity knowledge in a Neo4j graph and retrieves relevant context automatically on each turn.

**Key APIs:** `Neo4jOpenAIMemory`, `create_memory_tools()`, `execute_memory_tool()`, `record_agent_trace()`

> **Prerequisite:** This approach requires a **writable** Neo4j instance. Set the `MEMORY_NEO4J_*` environment variables described in the Configuration section.

```python
from neo4j_agent_memory import MemoryClient, MemorySettings, Neo4jConfig
from neo4j_agent_memory.integrations.openai_agents import (
    Neo4jOpenAIMemory, create_memory_tools, record_agent_trace,
)
from neo4j_agent_memory.integrations.openai_agents.memory import execute_memory_tool

# Initialise memory
mem_client = MemoryClient(settings)
memory = Neo4jOpenAIMemory(memory_client=mem_client, session_id="demo-session")

# Turn 1 — establish research context
await run_turn(memory, "I am conducting a competitive analysis of 'Google'. ...")

# Turn 2 — memory context from Turn 1 is surfaced automatically via get_context()
await run_turn(memory, "What are the main risks in the supply chain for the company I am currently tracking?")

# Persist the reasoning trace for future learning
await record_agent_trace(memory=memory, messages=conversation, task="...", success=True)
```

**Example output:**

```
[USER]: I am conducting a competitive analysis of 'Google'. I am specifically
        worried about their subsidiaries and who their top-tier competitors are in the AI space.

[AGENT]: Google's key subsidiaries include DeepMind, Waymo, and Verily.
         Top AI competitors include Microsoft (OpenAI partnership), Meta AI, Amazon (AWS AI), and Apple.

--- Indexing memory (5s)... ---

[USER]: What are the main risks in the supply chain for the company I am currently tracking?

[AGENT]: For Google, key supply chain risks include dependency on TSMC/Samsung for custom TPU chips,
         rare earth material sourcing for hardware, and hyperscale data centre power constraints.

  [Trace] Agent reasoning trace recorded to Neo4j.
```

**When to use:** You need agents that remember context across multiple sessions or conversations — ideal for research assistants, customer-facing agents, or any long-running workflow.

---

## Implementation Notes

| Topic | Detail |
|-------|--------|
| **MCP server credentials** | In HTTP mode, credentials are sent per-request via `Authorization: Basic ...` — not as server environment variables. |
| **`PatchedMCPServerStreamableHttp`** | Works around a v1.5.x `neo4j-mcp-server` bug where `get-schema` incorrectly declares `required: ["properties"]`. Can be removed once fixed upstream. |
| **`create_memory_tools()`** | Produces four OpenAI function-calling tools: `search_memory`, `save_preference`, `recall_preferences`, `search_entities`. |
| **`record_agent_trace()`** | Persists the full reasoning trace to Neo4j so the agent can learn from past interactions via `get_similar_traces()`. |

## Resources

- [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
- [OpenAI Agents SDK — MCP Support](https://openai.github.io/openai-agents-python/mcp/)
- [Neo4j Agent Memory — OpenAI Integration](https://neo4j.com/labs/agent-memory/how-to/integrations/openai-agents/)
- [neo4j-mcp-server on PyPI](https://pypi.org/project/neo4j-mcp-server/)
- [neo4j-agent-memory on PyPI](https://pypi.org/project/neo4j-agent-memory/)
- [Neo4j Python Driver Documentation](https://neo4j.com/docs/python-manual/current/)
