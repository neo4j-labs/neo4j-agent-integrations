# Microsoft Agent Framework + Neo4j

[Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/overview/) is Microsoft's open-source SDK for building production AI agents in Python and .NET — single agents, multi-agent workflows, and hosted-agent deployment.
Neo4j is the graph database and knowledge layer that grounds those agents in connected enterprise data.

This example wires them together as a multi-agent investment-research assistant: a **Coordinator** delegates to a **Database** agent (queries Neo4j) and an **Analyst** (synthesizes a report). One uv-runnable file. Reads `microsoft-foundry/.env` for the Foundry endpoint and Neo4j credentials.

Tool names and return shapes follow the [`EXAMPLE_AGENT.md`](../../../EXAMPLE_AGENT.md) spec ("Industry Research Agent").

## When to pick this path

- You want to see how Agent Framework composes multiple agents.
- A single fat agent with twenty tools loses focus — splitting work into a Database agent and an Analyst produces sharper, more grounded output.
- Function tools talk to Neo4j directly via the Bolt driver — no MCP server, no extra hop.

## Quick start

```bash
az login
cd microsoft-foundry/infra && ./deploy.sh    # one-time, opt in to Foundry
cd ../../microsoft-agent-framework/examples/multi-agent && uv run multi_agent_neo4j.py
```

`uv` reads the inline `# /// script` deps at the top of `multi_agent_neo4j.py` and runs. The script reads `microsoft-foundry/.env` for the Foundry endpoint, Azure tenant, and Neo4j credentials.

## The three agents

```mermaid
flowchart LR
    user["User"] --> coord
    subgraph agents["Multi-agent system"]
        coord["Coordinator Agent<br/>(delegates)"]
        db["Database Agent<br/>(10 Neo4j functions)"]
        analyst["Analyst Agent<br/>(no tools — synthesis)"]
    end
    coord -->|as_tool| db
    coord -->|as_tool| analyst
    db -->|neo4j Bolt driver| neo4j[("Neo4j Aura<br/>(companies demo graph)")]
```

| Agent | Tools | Job |
| --- | --- | --- |
| **Coordinator Agent** | `database_agent.as_tool()`, `analyst_agent.as_tool()` | Orchestrates: delegates one focused question per facet to the Database Agent, concatenates responses, passes to the Analyst Agent. Never queries the graph or writes the report itself. |
| **Database Agent** | 10 typed Neo4j functions | Calls the right tool for the request, returns one ```json``` block per call (raw rows verbatim — every `company_id`, `article_id`, title, date, sentiment, relationship type). No prose. |
| **Analyst Agent** | none | Reads the JSON blocks, produces a structured report: Executive Summary, Profile, Recent Developments, Network table, Risks & Outlook. Cites IDs verbatim from the rows. |

Composition is two `Agent.as_tool()` calls handed to the Coordinator's `tools=` — that's the whole multi-agent surface. The script is intentionally self-contained; [`../foundry-hosted/main.py`](../foundry-hosted/main.py) is a parallel near-identical file packaged for the Foundry hosted-agent runtime.

## Function tools (Neo4j)

Ten read-only functions over the public `companies` demo graph, organised the way the agent picks them — same set as [`microsoft-foundry/examples/foundry-sdk/`](../../../microsoft-foundry/examples/foundry-sdk/):

**Discovery** — `search_companies`, `list_industries`, `companies_in_industry`
**Profile** — `query_company`
**Network** — `analyze_relationships`, `people_at_company`
**News** — `search_news(company_name, query)` (vector — embeds `query` via [`OpenAIEmbeddingClient`](https://learn.microsoft.com/agent-framework/agents/providers/openai) against the Foundry `text-embedding-3-small` deployment, hits the demo graph's 1536-dim `news` index), `articles_in_month`, `get_article`, `companies_in_article`

Plain Python functions with type hints and docstrings. Agent Framework auto-converts them to function tools — no decorator, no schema boilerplate.

## Anti-hallucination contract

`as_tool()` only forwards the inner agent's text to the parent — easy for an inner agent to silently summarise IDs away. Three guarantees in the instructions:

1. **Database Agent** emits one fenced ```json``` block per tool call (`tool`, `args`, `rows`). No prose, no summaries.
2. **Coordinator** passes those JSON blocks verbatim into the Analyst's `task`. Never strips down to bare IDs.
3. **Analyst Agent** must cite every `company_id`, `article_id`, title, and relationship type from the rows. Real IDs look like `EIsFKrN_ZNLSWsvxdQfWutQ` / `ART11195006745` — short placeholders ("101", "AWS partnership") are flagged in the prompt as hallucination.

Result: every value in the report appears verbatim in a tool result.

## How it authenticates

- **You → Foundry:** [`AzureCliCredential`](https://learn.microsoft.com/python/api/azure-identity/azure.identity.azureclicredential) pinned to `AZURE_TENANT_ID` from `.env` so it works when `az login` is logged into multiple tenants.
- **You → Neo4j:** the `neo4j` Python driver with username/password from `.env`. Defaults to `companies` / `companies` against the public demo graph.

No Foundry tokens or Neo4j credentials are passed through the model — it sees only the tool schemas and the rows you return.

## Override knobs

Set these in `microsoft-foundry/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FOUNDRY_QUESTION` | "Research Microsoft's position…" | The single user question. Pick something that exercises both database and analyst. |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | `gpt-4o-mini` | Model to run all three agents on. |
| `NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | demo graph | Point at your own Aura or self-managed Neo4j. |
