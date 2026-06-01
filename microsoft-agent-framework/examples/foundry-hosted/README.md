# Foundry-hosted multi-agent — Microsoft Agent Framework + Neo4j

Same multi-agent investment-research graph as [`../multi-agent/`](../multi-agent/) — Coordinator + Database Agent + Analyst Agent — packaged as a [Foundry hosted agent](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents) via [`agent-framework-foundry-hosting`](https://pypi.org/project/agent-framework-foundry-hosting/) (`ResponsesHostServer`). Deployed with the canonical [`azd ai agent init -m`](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent) flow.

## Why host it?

Hosted agents take the same Agent Framework code you ran locally and put it on Foundry's managed runtime. From the [official concepts page](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents):

- **Bring your own code** — Agent Framework, LangGraph, custom; the platform doesn't care.
- **Dedicated agent identity** — a Microsoft Entra ID is auto-created at deploy and used by the agent at runtime to call models, tools, and downstream Azure services. No managed-identity wiring.
- **Per-session VM-isolated sandboxes** — `$HOME` and `/files` persist across turns and idle (15-min idle timeout, 30-day session lifetime).
- **Versioning** — immutable agent versions with weighted traffic split for canary and blue-green rollouts.
- **Scale-to-zero** — Foundry handles container lifecycle, scaling, and Application Insights observability.
- **Foundry portal integration** — playground, version management, and traces, no extra wiring.

## Files in this folder

Flat layout matching the canonical [agent-framework hosted samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/foundry-hosted-agents/responses):

| File | Purpose |
| --- | --- |
| `main.py` | The full agent definition (10 `@tool` functions + 3 instructions + Coordinator) plus `ResponsesHostServer().run()`. Self-contained on purpose; [`../multi-agent/multi_agent_neo4j.py`](../multi-agent/multi_agent_neo4j.py) is a parallel near-identical file for local dev. |
| `requirements.txt` | Python deps (split-package install — see local example README) |
| `Dockerfile` | `python:3.12-slim`, exposes port 8088 |
| `.dockerignore` | Excludes `.azure/`, `.env`, `__pycache__/`, etc. |
| `agent.yaml` | Hosted-agent definition (protocol, resources, env vars) |
| `agent.manifest.yaml` | Template metadata + model resource — `azd ai agent init -m` reads this |
| `.env.example` | What to set locally for `python main.py` |
| `README.md` | This file |

## Deploy

The flow below is the [canonical hosted-agents quickstart](https://learn.microsoft.com/azure/foundry/agents/quickstarts/quickstart-hosted-agent) — Microsoft's recommended path for shipping an Agent Framework agent to Foundry.

### Prerequisites

```bash
azd ext install azure.ai.agents      # 0.1.27-preview or newer required
az login
cd microsoft-foundry/infra && ./deploy.sh    # if you haven't already — provides the Foundry project
```

`microsoft-foundry/infra/deploy.sh` deploys to Sweden Central by default — a hosted-agents-supported region — so the same project can host this example.

### Deploy

```bash
# Resolve the Foundry project ID from the microsoft-foundry/ deployment
PROJECT_ID="$(az resource list \
  --resource-type 'Microsoft.CognitiveServices/accounts/projects' \
  --query "[?starts_with(name, 'aif-foundry-neo4j')].id | [0]" -o tsv)"

mkdir my-research-agent && cd my-research-agent

# 1. Scaffold the azd starter (provides infra/main.bicep)
azd init -t Azure-Samples/azd-ai-starter-basic --location swedencentral

# 2. Add the agent on top, pointing at the existing Foundry project + model
azd ai agent init \
  -m https://raw.githubusercontent.com/<owner>/neo4j-agent-integrations/feature/agent-framework/microsoft-agent-framework/examples/foundry-hosted/agent.manifest.yaml \
  -p "$PROJECT_ID" \
  -d gpt-4o-mini

# 3. Wire Neo4j (defaults connect to the public companies demo graph) +
#    the embedding deployment that microsoft-foundry/infra/ provisioned
azd env set NEO4J_URI                       "neo4j+s://demo.neo4jlabs.com:7687"
azd env set NEO4J_DATABASE                  "companies"
azd env set NEO4J_USERNAME                  "companies"
azd env set NEO4J_PASSWORD                  "companies"
azd env set FOUNDRY_EMBEDDING_DEPLOYMENT_NAME "text-embedding-3-small"

# 4. Build container, register agent against the existing Foundry project
azd up
```

End-to-end takes ~2-3 minutes. `azd up` prints the agent endpoint and a Foundry portal playground link. The hosted runtime lives in the **same Foundry project** as the Neo4j MCP container app — one deployment, both use cases.

> **`-m` takes a file path, not a folder.** Some Microsoft docs suggest a folder works — the CLI rejects it with `"is a directory, not a manifest file"`. Always point at the `agent.manifest.yaml` file (or its raw GitHub URL).

### Test the deployed agent

```bash
azd ai agent invoke "Research Microsoft's position in the software industry. Gather company profile, recent news, and key relationships, then synthesize an investment outlook."
```

You'll see a structured report — Executive Summary, Company Profile, Recent Developments, Network table, Risks & Outlook — with every `company_id` and `article_id` cited verbatim from the graph (real IDs like `EFhu1XwygPsKq_UjZtDFwXQ` and `ART11195006745`, not made-up placeholders).

Open the agent in the Foundry portal playground via the link printed by `azd up`.

### Tear down

```bash
# This removes the agent + ACR provisioned by THIS folder. The shared
# Foundry account/project from microsoft-foundry/ stays alive — purge
# (`--purge`) would also delete the shared account, so leave it off.
azd down --no-prompt
```

To remove the entire shared deployment as well, run `azd down --purge --no-prompt` from `microsoft-foundry/infra/` afterwards.

## Running locally first (optional sanity check)

Before paying for a deployment, run the same code on your laptop:

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env to fill in FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME
# (the Neo4j defaults already point at the demo graph)
az login
python main.py
```

The server listens on `http://localhost:8088`. In another terminal:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Research Microsoft. Profile, news, relationships, then an investment outlook."}'
```

You'll see the same multi-agent flow as the local example — Coordinator → Database Agent (multiple Neo4j tool calls) → Analyst Agent — synthesizing a faithful, ID-cited report.

## Security note

Per the official [hosted-agents docs](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents): "Don't put secrets in container images or environment variables. Use managed identities and connections, and store secrets in a managed secret store."

This sample stores Neo4j credentials in `azd env` (which writes them to `.azure/<env>/.env`) for demo-graph simplicity (`companies`/`companies` is public). For BYO Neo4j (Aura), wire credentials through a [Key Vault connection](https://learn.microsoft.com/azure/foundry/how-to/set-up-key-vault-connection) and reference them from `agent.yaml` instead of plain env vars.

## How it differs from `../multi-agent/`

Same agent graph, three differences in `main.py`:

1. **Tool decorator** — every Neo4j function is wrapped in `@tool(approval_mode="never_require")` with `Annotated[..., Field(description=...)]` parameter docs. Hosted agents default to requiring approval for tool calls; we opt out so the multi-agent flow runs unattended.
2. **Credential** — `DefaultAzureCredential()` (the agent's Microsoft Entra ID at runtime, your `az login` locally), instead of `AzureCliCredential(tenant_id=...)`.
3. **`default_options={"store": False}`** on the coordinator — the hosting platform owns conversation history; don't double-persist on the OpenAI Responses side.

That's it. The multi-agent composition (Coordinator + Database Agent + Analyst Agent via `as_tool()`) and the anti-hallucination contract (JSON blocks per tool call, raw rows verbatim) are identical.
