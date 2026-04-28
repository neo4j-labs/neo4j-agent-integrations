# Foundry SDK + Neo4j Function Tools — Python

Same investment research agent as the [portal walkthrough](../mcp/), driven from code with the **Foundry SDK Responses API**. Tools are narrow Python functions that run pre-baked Cypher against Neo4j directly — your app owns every query. No MCP server, no generic `read-cypher` exposed to the model.

Tool names and return shapes follow the [`EXAMPLE_AGENT.md`](../../../EXAMPLE_AGENT.md) spec ("Industry Research Agent"). Cypher uses the actual `companies` demo schema underneath.

## When to pick this path

- You want tight control over which graph queries the model can run.
- Connection pooling and secrets stay on the app side.
- Every query is a literal Python function you wrote — easy to audit, easy to add.

For a reusable MCP endpoint that any Foundry / Copilot Studio / Agent Framework agent can attach, use [`examples/mcp`](../mcp/) instead.

## Run

```bash
cd microsoft-foundry/infra
./deploy.sh                    # one-time, opt in to Foundry at the prompt

cd ../examples/foundry-sdk
uv run foundry_sdk_neo4j.py
```

`uv` reads the inline dependency block at the top of the script (`azure-ai-projects`, `azure-identity`, `openai`, `python-dotenv`, `neo4j`), provisions an isolated environment, and runs. No `requirements.txt`, no virtualenv, no exports. The script reads `microsoft-foundry/.env` for everything (Foundry endpoint, Azure tenant, Neo4j credentials).

## Function tools

Three narrow read-only functions over the public `companies` demo graph:

| Tool | Returns | Cypher behind it |
| --- | --- | --- |
| `query_company(company_name)` | `{name, industries, locations, leadership}` | `(:Organization)` joined to `IndustryCategory` (`HAS_CATEGORY`), `City`/`Country` (`IN_CITY`/`IN_COUNTRY`), `Person` (`HAS_CEO`/`HAS_BOARD_MEMBER`) |
| `companies_in_industry(industry)` | `[{name}]` | `(:IndustryCategory)<-[:HAS_CATEGORY]-(:Organization)` |
| `search_news(company_name)` | `[{title, date, sentiment}]` | `(:Article)-[:MENTIONS]->(:Organization)` |

To add a tool: write a Python function with one string parameter and a docstring, then add it to `TOOL_IMPLS`. The `function_tool()` helper auto-generates the strict JSON schema from the function's signature and docstring.

## Expected output

```
> Tell me about Microsoft — its industry, who runs it, and where it's
  based. Then suggest three peers in the same industry.
  → query_company(company_name='Microsoft')
  → companies_in_industry(industry='Software Companies')

Microsoft operates in: Manufacturing, Enterprise Software, Business
Software, Software Companies. CEO: Satya Nadella. Locations include
Mississauga, Halifax, Calgary. Peers in Software Companies: Sutter Mills,
Ivalua, Catchpoint Systems.
```

## How it authenticates

- **You → Foundry:** [`AzureCliCredential`](https://learn.microsoft.com/python/api/azure-identity/azure.identity.azureclicredential) pinned to `AZURE_TENANT_ID` from `.env` so it works when `az login` is logged into multiple tenants.
- **You → Neo4j:** the `neo4j` Python driver with username/password from `.env`. Defaults to `companies` / `companies` against the public demo graph.

No Foundry tokens or Neo4j credentials are passed through the model — it sees only the tool schemas and the rows you return.

## Override knobs

Set these in `microsoft-foundry/.env`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FOUNDRY_QUESTION` | "Tell me about Microsoft…" | The single user question. |
| `FOUNDRY_TEST_AGENT_NAME` | `neo4j-research-agent-sdk` | Agent version name (created and deleted each run). |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | `gpt-4o-mini` | Model to run the agent on. |
| `NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | demo graph | Point at your own Aura or self-managed Neo4j. |

## Coming later

Additional tools to layer in: `search_companies` (full-text), `analyze_relationships` (multi-hop graph traversal), `find_influential_companies` (PageRank), `articles_in_month`, `get_article`, `people_at_company`. Plus a C# version, a streaming variant, and conversation persistence.
