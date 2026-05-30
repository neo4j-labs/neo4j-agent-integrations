# Foundry-hosted multi-agent - Microsoft Agent Framework + Neo4j

This example packages the multi-agent investment-research graph from [`../multi-agent/`](../multi-agent/) as a [Foundry hosted agent](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents). The graph follows [`EXAMPLE_AGENT.md`](../../../EXAMPLE_AGENT.md): a coordinator delegates to a Neo4j database agent and an analyst agent through Agent Framework's agents-as-tools pattern. It is served through `ResponsesHostServer` from [`agent-framework-foundry-hosting`](https://pypi.org/project/agent-framework-foundry-hosting/).

## Why host it?

Hosted agents run the same Agent Framework code on Foundry's managed runtime. The hosted runtime provides:

- Support for custom agent code, including Agent Framework and LangGraph applications.
- A dedicated Microsoft Entra identity for the hosted agent.
- Per-session isolated sandboxes for runtime state.
- Immutable agent versions.
- Managed container lifecycle and scale-to-zero behavior.
- Portal access for playground testing, version management, monitoring, and traces.

## Files in this folder

The example uses a flat layout that matches the [Agent Framework hosted samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/04-hosting/foundry-hosted-agents/responses):

| File | Purpose |
| --- | --- |
| `main.py` | Defines the hosted agent graph: Neo4j tools, database-agent instructions, analyst instructions, coordinator, credentials, and `ResponsesHostServer().run()`. It is self-contained so the hosted sample can be scaffolded by `azd`; [`../multi-agent/multi_agent_neo4j.py`](../multi-agent/multi_agent_neo4j.py) contains the local-only variant. |
| `requirements.txt` | Python dependencies. The sample installs the Agent Framework split packages directly to avoid importing the empty `agent-framework` meta-package. |
| `Dockerfile` | Container image for hosted deployment. It uses `python:3.12-slim`, installs `requirements.txt`, exposes port 8088, and starts `main.py`. |
| `.dockerignore` | Keeps local environment files, azd state, caches, and virtual environments out of the container build context. |
| `agent.yaml` | Hosted-agent definition used after scaffolding: agent name, protocol, resource limits, and runtime environment variables. |
| `agent.manifest.yaml` | Manifest template used by `azd ai agent init -m` to generate the azd project and bind the model deployment. |
| `.env.example` | Local environment template for running `python main.py` directly during development. |
| `README.md` | Setup, local run, deployment, test, and cleanup instructions. |

## Quick demo

The recommended demo path is to scaffold an `azd` project from the manifest, point it at the existing Foundry project, and run it locally with `azd ai agent run`. This validates the hosted-agent runtime before provisioning container hosting resources.

### Prerequisites

```bash
azd ext install azure.ai.agents
az login
cd microsoft-foundry/infra && ./deploy.sh    # if needed; provides the Foundry project
```

`microsoft-foundry/infra/deploy.sh` deploys to Sweden Central by default, which supports hosted agents. Docker is not required for the local `azd ai agent run` path. The managed deployment path below uses remote ACR build, so Docker is not required locally for `azd up` either.

### Run locally with the hosted-agent runtime

```bash
repo_root="$(git rev-parse --show-toplevel)"
manifest_path="$repo_root/microsoft-agent-framework/examples/foundry-hosted/agent.manifest.yaml"

# Reuse the shared Foundry deployment metadata written by
# microsoft-foundry/infra/deploy.sh
. "$repo_root/microsoft-foundry/.env"

PROJECT_ID="${FOUNDRY_PROJECT_ID:-/subscriptions/$AZURE_SUBSCRIPTION_ID/resourceGroups/$FOUNDRY_RESOURCE_GROUP/providers/Microsoft.CognitiveServices/accounts/$FOUNDRY_ACCOUNT_NAME/projects/$FOUNDRY_PROJECT_NAME}"
MODEL_DEPLOYMENT_NAME="$FOUNDRY_MODEL_DEPLOYMENT_NAME"

cd "$repo_root/microsoft-agent-framework/examples"
mkdir -p azd-workspace/foundry-hosted && cd azd-workspace/foundry-hosted

# 1. Scaffold the hosted-agent azd project against the existing Foundry
#    project + model.
azd ai agent init \
  -m "$manifest_path" \
  -p "$PROJECT_ID" \
  -d "$MODEL_DEPLOYMENT_NAME" \
  --agent-name neo4j-research-agent-framework \
  --no-prompt

cd neo4j-research-agent-framework

# 2. Configure Neo4j (defaults connect to the public companies demo graph)
#    and the embedding deployment.
azd env set NEO4J_URI                       "neo4j+s://demo.neo4jlabs.com:7687"
azd env set NEO4J_DATABASE                  "companies"
azd env set NEO4J_USERNAME                  "companies"
azd env set NEO4J_PASSWORD                  "companies"
azd env set AZURE_TENANT_ID                 "$(az account show --query tenantId -o tsv)"
azd env set EMBEDDING_DEPLOYMENT_NAME         "text-embedding-3-small"

# 3. Run the hosted-agent runtime locally.
azd ai agent run --no-inspector
```

In another terminal:

```bash
azd ai agent invoke --local --new-session --timeout 600 \
  "Research Microsoft's position in the software industry. Gather company profile, recent news, and key relationships, then synthesize an investment outlook."
```

`azd ai agent invoke --local` sends a request to the locally running hosted-agent runtime. `--new-session` keeps repeated demo runs isolated instead of reusing the prior conversation automatically.

For local runs, this sample now prefers `AzureCliCredential` when the Azure CLI is available, then falls back to `DefaultAzureCredential` for hosted deployment scenarios. Setting `AZURE_TENANT_ID` in the `azd` environment keeps local auth deterministic when your CLI can see multiple tenants.

The response is a structured report with an Executive Summary, Company Profile, Recent Developments, Network table, and Risks & Outlook. IDs such as `company_id` and `article_id` are taken directly from the graph rows.

## Deploy to Foundry (optional)

If you want a managed endpoint in Foundry after validating the demo locally, run:

```bash
azd up
```

from `microsoft-agent-framework/examples/azd-workspace/foundry-hosted/neo4j-research-agent-framework`.

This provisions the hosting resources for the sample, builds and pushes the container image, and registers a hosted agent version in the selected Foundry project.

Test the hosted agent from the CLI with a longer timeout:

```bash
azd ai agent invoke neo4j-research-agent-framework \
  --new-session \
  --timeout 600 \
  "Research Microsoft's position in the software industry. Gather company profile, recent news, and key relationships, then synthesize an investment outlook."
```

The Foundry Playground is useful for short smoke tests. For the full prompt above, prefer `azd ai agent invoke`; the agent graph performs several model and Neo4j tool calls, and the Playground may show a generic network timeout before the hosted agent finishes.

After deployment, stream the hosted-agent logs with:

```bash
azd ai agent monitor --follow
```

### Tear down

```bash
# Remove the local scaffold created by this README.
rm -rf microsoft-agent-framework/examples/azd-workspace/foundry-hosted/neo4j-research-agent-framework
```

This example reuses the shared Foundry project from `microsoft-foundry/infra/`. Do not run `azd down` from the scaffold unless you have reviewed the deletion plan and intend to remove the listed shared resources. For Azure cleanup, delete only the hosted agent/version or sample-specific resources you created.

## How it differs from `../multi-agent/`

The hosted sample uses the same agent graph as `../multi-agent/`, with three hosted-runtime differences:

1. **Tool approval** - Neo4j functions use `@tool(approval_mode="never_require")` with `Annotated[..., Field(description=...)]` parameter descriptions so the hosted agent can run unattended.
2. **Credentials** - local runs prefer `AzureCliCredential` when the Azure CLI is available, with `DefaultAzureCredential` as the hosted-runtime fallback.
3. **Response storage** - each hosted agent uses `default_options={"store": False}` because the hosting platform owns conversation history.

The multi-agent composition and the row-grounded reporting contract are otherwise the same.
