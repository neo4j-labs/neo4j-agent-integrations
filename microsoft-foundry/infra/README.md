# Neo4j MCP Server on Azure

Deploy the official Neo4j MCP server to Azure Container Apps. This is shared infrastructure for Foundry, Copilot Studio, Microsoft Agent Framework, and any other MCP client.

## Prerequisites

- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- An Azure subscription with permission to create resource groups, Container Apps environments, and Log Analytics workspaces
- For the smoke test (`test-mcp.sh`): `curl` and `base64` (default on macOS and Linux)

Sign in once. Most setups have azd configured to inherit the Azure CLI token, so `az login` is the safe default and is also what the Foundry role assignment relies on:

```bash
az login
```

If `azd` is configured in its standalone auth mode (no warning when you run `azd auth login`), use `azd auth login` instead. If unsure, run both — they don't conflict.

## Quick Start

```bash
./deploy.sh
./test-mcp.sh "$(azd env get-value mcpEndpoint)"
```

`deploy.sh` is the canonical entry point. It runs `azd up` under the hood, then writes a shared `microsoft-foundry/.env` that every example script under `microsoft-foundry/examples/*` sources — so you don't export variables by hand. The file carries:

- `NEO4J_MCP_ENDPOINT` — the deployed MCP server URL.
- `NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` — Neo4j connection (Basic auth header for the MCP server).
- `FOUNDRY_RESOURCE_GROUP` / `FOUNDRY_ACCOUNT_NAME` / `FOUNDRY_PROJECT_NAME` / `FOUNDRY_PROJECT_ENDPOINT` / `FOUNDRY_MODEL_DEPLOYMENT_NAME` — auto-filled when you opt in to Foundry provisioning at the deploy.sh prompt. Empty if you opted out; edit `microsoft-foundry/.env` directly in that case to point at your existing Foundry project. Either way, re-running `./deploy.sh` preserves any non-empty values you've set.

No Foundry auth secrets live in the `.env`. The Python example authenticates via `az login` (`AzureCliCredential` pinned to the `AZURE_TENANT_ID` written above, so it works when your `az` is signed into multiple tenants). See [`microsoft-foundry/.env.example`](../.env.example) for the full schema.

`azd up` prompts for three things on first run:

| Prompt | Meaning | Examples |
| --- | --- | --- |
| **Environment name** | Suffix added to every resource name. Pick a stage or instance label. | `dev`, `prod`, `chris-pr` |
| **Subscription** | Azure subscription to deploy into. | — |
| **Location** | Azure region for the resource group. | `eastus2`, `westeurope` |

The Bicep is subscription-scoped, so `azd` does not prompt for or require a pre-existing resource group — it creates `rg-foundry-neo4j-<env>` for you.

## What Gets Deployed

For environment name `dev`:

- Resource group: `rg-foundry-neo4j-dev`
- Log Analytics workspace: `log-foundry-neo4j-dev`
- Container Apps environment: `cae-foundry-neo4j-dev`
- Container App: `ca-foundry-neo4j-dev`
- Public HTTPS MCP endpoint: `https://<container-app-fqdn>/mcp`

An azd `preprovision` hook ([`hooks/preprovision.sh`](./hooks/preprovision.sh)) prompts whether to also provision Microsoft Foundry. When you answer yes, the deployment also creates:

- Microsoft Foundry account: `aif-foundry-neo4j-dev-<4-char-hash>` (`Microsoft.CognitiveServices/accounts`, kind `AIServices`, with `allowProjectManagement: true`). The hash is derived from the resource group ID + workload, deterministic per deploy, and protects the globally-unique custom subdomain from collisions when multiple people run this template.
- Foundry project: `proj-foundry-neo4j-dev`
- Model deployment: `gpt-4o-mini` (version `2024-07-18`, `GlobalStandard`, capacity 30)
- Azure AI Developer role assignment for the signed-in user on the Foundry account, so `az login` is all the auth the examples need

Foundry agent APIs are only available in a small set of regions (`eastus`, `eastus2`, `swedencentral`, `westus`, `westus3`). Pick one of those at the location prompt — otherwise `azd up` may succeed but agent runs will fail.

## Configuration

Defaults connect to the public Neo4j `companies` demo graph. To override deployment knobs (different Neo4j database, private ingress, custom container image, etc.), copy this folder's `.env.sample` to a sibling `.env` *before* running `./deploy.sh`:

```bash
cp .env.sample .env            # both files live in microsoft-foundry/infra/
# edit .env
./deploy.sh
```

> Note: this `infra/.env` is the **deployment-time override** for `azd up`. It's distinct from the `microsoft-foundry/.env` that `deploy.sh` writes for the examples after deployment.

`deploy.sh` forwards every key in `infra/.env` into the azd environment, then provisions. Re-running `./deploy.sh` after editing it updates the deployment in place.

If you'd rather skip the wrapper, run `azd up` directly and call `azd env set <KEY> <VALUE>` yourself for any overrides — but the shared `microsoft-foundry/.env` won't be written, so example scripts won't pick up the deployed endpoint automatically.

Important knobs (full list in `infra/.env.sample`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEO4J_URI` | demo DB | Neo4j Bolt URI. |
| `NEO4J_DATABASE` | `companies` | Neo4j database. |
| `NEO4J_READ_ONLY` | `true` | Read-only MCP tools. Set `false` to enable writes. |
| `NEO4J_MCP_CONTAINER_IMAGE` | `mcp/neo4j:latest` | Pin a tested tag for production. |
| `MCP_EXTERNAL_INGRESS` | `true` | Public HTTPS ingress. Set `false` for private/internal. |
| `MCP_MIN_REPLICAS` | `1` | Warm endpoint. Set `0` if cold starts are acceptable. |

## Authentication Model

In HTTP mode, the Neo4j MCP server is stateless and expects auth on each request. It supports Basic auth and Bearer token pass-through:

```text
Authorization: Basic <base64(username:password)>
Authorization: Bearer <token>
```

Basic auth is the right default for the `companies` demo graph and direct Neo4j username/password access. Bearer token auth is for Neo4j Enterprise or Aura databases configured for SSO/OIDC; the MCP server forwards the token to Neo4j and does not perform an OAuth flow itself.

For Foundry MCP tools, create a project connection that injects the `Authorization` header. For OAuth client credentials, user delegation, policy, or token exchange, put a gateway such as Azure API Management in front of this server.

## Smoke Test

```bash
export NEO4J_USERNAME=companies
export NEO4J_PASSWORD=companies
./test-mcp.sh "$(azd env get-value mcpEndpoint)"
```

Expected tools:

- `get-schema`
- `read-cypher`

## Troubleshooting

**`./deploy.sh` hangs.** Almost always an auth issue. If `azd` is in `az cli` auth mode (it prints a warning when you run `azd auth login`) and `az` itself isn't logged in, `azd up` silently waits on a token refresh. Run `az login` and re-run.

**Foundry was provisioned but the smoke test or examples return 403.** The Azure AI Developer role assignment depends on `AZURE_PRINCIPAL_ID` being populated. azd populates it for you in standalone auth mode, but in `az cli` auth mode it can be empty, so the bicep skipped the role assignment. Fix:

```bash
azd env set AZURE_PRINCIPAL_ID "$(az ad signed-in-user show --query id -o tsv)"
azd env set AZURE_PRINCIPAL_TYPE User
./deploy.sh
```

The next `./deploy.sh` re-runs `azd up`, which is idempotent — it only adds the missing role assignment.

**`azd up` fails with `DeploymentModelNotSupported` or a quota error.** The default model `gpt-4o-mini` (version `2024-07-18`) is broadly available, but other models or specific regions may not have it. Foundry agent APIs are supported in `eastus`, `eastus2`, `swedencentral`, `westus`, and `westus3`. To use a different model, override before running `./deploy.sh`:

```bash
azd env set FOUNDRY_MODEL_NAME gpt-5-mini
azd env set FOUNDRY_MODEL_VERSION 2025-08-07
./deploy.sh
```

## Tear Down

```bash
azd down --force --purge
```

Deletes the resource group and everything in it. `--force` skips the confirmation prompt; `--purge` empties the Log Analytics workspace's soft-delete bucket so the same environment name can be redeployed cleanly. Expect 3–5 minutes for Container Apps to drain.

To start completely fresh (new env name, new prompt flow), also remove the local azd state:

```bash
rm -rf .azure
```

## References

- [Azure Developer CLI environment variables](https://learn.microsoft.com/azure/developer/azure-developer-cli/manage-environment-variables)
- [Azure resource abbreviations](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations)
- [Subscription-scoped Bicep deployments](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-to-subscription)
