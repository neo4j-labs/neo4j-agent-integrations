# Foundry SDK + Neo4j Function Tools — Python

Same investment research agent as the [portal walkthrough](../mcp/), but driven from code with the **Foundry SDK Responses API**. Tools are narrow Python functions that run pre-baked Cypher against Neo4j directly — your app owns every query. No MCP server in the loop, no generic `read-cypher` exposed to the model.

## When to pick this path

- You want tight control over which graph queries the model can run.
- You want secrets and connection pooling on the app side, not in a Foundry connection.
- You want precise audit/trace of every query — they're literal Python functions you wrote.
- You're shipping an app that drives the agent loop, not a tool surface other agents reuse.

If you instead want one MCP endpoint that any Foundry agent (or Copilot Studio, Agent Framework, etc.) can attach, use [`examples/mcp`](../mcp/).

## Run

If you haven't already:

```bash
cd microsoft-foundry/infra
./deploy.sh                    # answer "Y" at the Foundry prompt
```

Then:

```bash
cd microsoft-foundry/examples/foundry-sdk
uv run foundry_sdk_neo4j.py
```

`uv` reads the inline dependency metadata at the top of the script (`azure-ai-projects`, `azure-identity`, `openai`, `python-dotenv`, `neo4j`), sets up an isolated environment, and runs. No `requirements.txt`, no virtualenv, no exports.

The script:

1. Loads `microsoft-foundry/.env`.
2. Creates an agent version (`neo4j-research-agent-sdk`) on the deployed model with three function tools registered.
3. Asks a multi-hop research question (override with `FOUNDRY_QUESTION`).
4. Loops on the Responses API: every `function_call` item gets executed locally and submitted back as `function_call_output`.
5. Prints the final answer and deletes the agent version.

## Function tools

| Tool | Cypher behind it | Use |
| --- | --- | --- |
| `find_company(name)` | `MATCH (o:Organization {name})` joined to `Industry`, `Location`, `Person` via `IN_INDUSTRY`, `LOCATED_IN`, `WORKS_FOR` | One-shot company profile. |
| `list_industry_peers(company, limit)` | `(:Organization)-[:IN_INDUSTRY]->()<-[:IN_INDUSTRY]-(peer:Organization)` | Peer / competitor discovery. |
| `list_articles_about(company, limit)` | `(:Article)-[:MENTIONS]->(:Organization)` | News angle. |

Each tool is a Python function in `foundry_sdk_neo4j.py` — read them, change them, add new ones. Re-run the script; the new tool definition is picked up on the next agent version.

## How it authenticates

- **You → Foundry:** [`DefaultAzureCredential`](https://learn.microsoft.com/azure/developer/python/sdk/authentication/credential-chains#defaultazurecredential-overview), which picks up `az login` (or `azd auth login`).
- **You → Neo4j:** the `neo4j` Python driver with `NEO4J_USERNAME` / `NEO4J_PASSWORD` from the shared `.env`. Defaults to `companies` / `companies` against the public demo graph.

No Foundry tokens or Neo4j credentials are passed through the model — the model sees only the tool schemas and the rows you return.

## Override knobs

Defaults in `microsoft-foundry/.env` are usually enough. Override these in the same file to customise:

| Variable | Default | Purpose |
| --- | --- | --- |
| `FOUNDRY_QUESTION` | "Tell me about Google…" | The single user question the agent gets. |
| `FOUNDRY_TEST_AGENT_NAME` | `neo4j-research-agent-sdk` | Name of the agent version that gets created and deleted. |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | `gpt-4o-mini` | Model deployment to run the agent on. |
| `NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` | demo graph | Point at your own Aura or self-managed Neo4j. |

## Coming later

- C# version of the same flow with `Azure.AI.Projects` and `ResponseTool.CreateFunctionTool`.
- Streaming variant — process `response.output_text_delta` events as they arrive.
- Conversation persistence — turn the one-shot demo into a multi-turn chat using `openai.conversations.create`.
- Observability — Foundry traces + structured logging on each tool call.
