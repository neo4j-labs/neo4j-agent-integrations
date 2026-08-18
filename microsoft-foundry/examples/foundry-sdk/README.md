# Foundry SDK + Neo4j Function Tools — Python

Investment research agent driven from code with the **Foundry SDK Responses API**. Tools are narrow Python functions that run pre-baked Cypher against Neo4j directly — your app owns every query. No MCP server, no generic `read-cypher` exposed to the model.

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

Ten read-only functions over the public `companies` demo graph, organised the way the agent picks them:

**Discovery**

| Tool | Returns |
| --- | --- |
| `search_companies(search)` | up to 20 fuzzy name matches via the `entity` full-text index, ranked by score |
| `list_industries()` | every `IndustryCategory` name, alphabetical |
| `companies_in_industry(industry)` | up to 10 companies in a category, with `company_id` |

**Profile**

| Tool | Returns |
| --- | --- |
| `query_company(company_name)` | primary lookup: `company_id`, `name`, `industries`, `locations`, `leadership` (CEO + board) |

**Network**

| Tool | Returns |
| --- | --- |
| `analyze_relationships(company_name)` | 1–2 hop org-to-org connections (`HAS_SUBSIDIARY`, `HAS_SUPPLIER`, `HAS_COMPETITOR`, `HAS_INVESTOR`, …) with relationship types and distance |
| `people_at_company(company_id)` | people associated with the company and their roles |

**News**

| Tool | Returns |
| --- | --- |
| `search_news(company_name)` | up to 5 articles mentioning the company, with `article_id` |
| `articles_in_month(date)` | up to 25 articles in the calendar month starting at `yyyy-mm-dd` |
| `get_article(article_id)` | full article body (joined from chunks), summary, sentiment, source |
| `companies_in_article(article_id)` | companies mentioned in an article, with `company_id` |

To add a tool: write a Python function with typed parameters and a docstring, then add it to `TOOL_IMPLS`. The `function_tool()` helper auto-generates the strict JSON schema from the function's signature and docstring.

## Expected output

```text
> Tell me about Microsoft — its industry, who runs it, and where it's
  based. Then suggest three peers in the same industry.
  → query_company(company_name='Microsoft')
  → companies_in_industry(industry='Software Companies')

### Microsoft Overview
- **Industry**: Software Companies
- **Leadership**: CEO is **Satya Nadella**
- **Headquarters Locations**: Mississauga, Halifax, Calgary

### Suggested Peers in the Software Industry:
1. **Sutter Mills**
2. **Ivalua**
3. **Catchpoint Systems**
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
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | `gpt-5-mini` | Model to run the agent on. |
| `NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | demo graph | Point at your own Aura or self-managed Neo4j. |

## Coming later

The spec also defines a vector-search variant of `search_news` and `find_influential_companies` (PageRank). Both are intentionally out of scope here:

- **Vector `search_news`** — `deploy.sh` now provisions a `text-embedding-3-small` deployment too, so the building block is there. This example deliberately keeps the simpler MENTIONS-based version; see [`microsoft-agent-framework/examples/multi-agent`](../../../microsoft-agent-framework/examples/multi-agent/) for the vector-search variant.
- **`find_influential_companies`** uses Neo4j Graph Data Science with write access to project an in-memory graph; the public demo database is read-only.
