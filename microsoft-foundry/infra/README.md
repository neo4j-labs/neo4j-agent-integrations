# Neo4j MCP Server on Azure

Deploy the official Neo4j MCP server to Azure Container Apps.
This is shared infrastructure for Foundry, Copilot Studio,
Microsoft Agent Framework, and any other MCP client.

## Prerequisites

- [Azure CLI (`az`)](https://learn.microsoft.com/cli/azure/install-azure-cli)
- [Azure Developer CLI (`azd`)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- An Azure subscription with permission to create resource groups,
  Container Apps environments, and Log Analytics workspaces
- For the smoke test (`test-mcp.sh`): `curl` and `base64`
  (default on macOS and Linux)

Sign in before deploying:

```bash
az login
```

If `azd` uses standalone auth in your environment, run `azd auth login` as well.

## Quick Start

```bash
./deploy.sh
./test-mcp.sh "$(azd env get-value mcpEndpoint)"
```

`deploy.sh` runs `azd up` and writes `microsoft-foundry/.env`.
All example scripts under `microsoft-foundry/examples/*` source that file.
It contains:

- `NEO4J_MCP_ENDPOINT` — the deployed MCP server URL.
- `NEO4J_URI` / `NEO4J_DATABASE` / `NEO4J_USERNAME` /
  `NEO4J_PASSWORD` — Neo4j connection used by the MCP server.
- `FOUNDRY_RESOURCE_GROUP` / `FOUNDRY_ACCOUNT_NAME` /
  `FOUNDRY_PROJECT_NAME` / `FOUNDRY_PROJECT_ENDPOINT` /
  `FOUNDRY_MODEL_DEPLOYMENT_NAME` — populated when you opt in
  to Foundry provisioning. If you opt out, set these in
  `microsoft-foundry/.env` to point at an existing Foundry
  project. Re-running `./deploy.sh` preserves any non-empty
  values you already set.

No Foundry secrets are stored in `.env`.
The Python example uses `AzureCliCredential` from your `az login`
session. See [`microsoft-foundry/.env.example`](../.env.example)
for the full schema.

`azd up` prompts on first run unless these are already set in the
azd env. `deploy.sh` defaults `AZURE_LOCATION` to `swedencentral` so
the same Foundry project can later host the agent-framework
[`foundry-hosted`](../../microsoft-agent-framework/examples/foundry-hosted/)
example without having to redeploy in a different region.

| Prompt | Meaning | Default | Examples |
| --- | --- | --- | --- |
| **Environment name** | Resource suffix. | — | `dev`, `prod` |
| **Subscription** | Azure subscription to deploy into. | — | — |
| **Location** | Azure region. | `swedencentral` | `northcentralus`, `eastus2` |

If you don't need hosted agents and want a different region, override
with `azd env set AZURE_LOCATION <region>` before `./deploy.sh`. For
hosted-agent compatibility, stick to Sweden Central, North Central US,
Canada Central, or Australia East ([current list](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)).

The Bicep is subscription-scoped, so `azd` creates
`rg-foundry-neo4j-<env>` for you.

## What Gets Deployed

For environment name `dev`:

- Resource group: `rg-foundry-neo4j-dev`
- Log Analytics workspace: `log-foundry-neo4j-dev`
- Container Apps environment: `cae-foundry-neo4j-dev`
- Container App: `ca-foundry-neo4j-dev`
- Public HTTPS MCP endpoint: `https://<container-app-fqdn>/mcp`

An azd `preprovision` hook
([`hooks/preprovision.sh`](./hooks/preprovision.sh)) asks whether
to also provision Microsoft Foundry. If you answer yes, the
deployment also creates:

- Microsoft Foundry account:
  `aif-foundry-neo4j-dev-<4-char-hash>`
  (`Microsoft.CognitiveServices/accounts`, kind `AIServices`,
  with `allowProjectManagement: true`)
- Foundry project: `proj-foundry-neo4j-dev`
- Model deployment: `gpt-5-mini`
  (version `2025-08-07`, `GlobalStandard`, capacity 120)
- Foundry User role assignment for the signed-in user on the
  Foundry **project**, so `az login` is all the auth the examples
  need (create/run agents, call models via the project endpoint)

The hash keeps the account's custom subdomain globally unique
while remaining deterministic for the same deployment inputs.

Before deploying, confirm that Foundry and your target model
are available in the selected region.

## Configuration

Defaults connect to the public Neo4j `companies` demo graph.
To override deployment settings such as the Neo4j database,
ingress mode, or container image, copy this folder's `.env.sample`
to `.env` before running `./deploy.sh`:

```bash
cp .env.sample .env
# edit .env
./deploy.sh
```

Both files live in `microsoft-foundry/infra/`.

> Note: `infra/.env` is the deployment-time override for `azd up`.
> It is separate from `microsoft-foundry/.env`, which `deploy.sh`
> writes for the examples after deployment.

`deploy.sh` forwards every key in `infra/.env` into the azd
environment, then provisions. Re-running `./deploy.sh` after
editing it updates the deployment in place.

You can run `azd up` directly and manage overrides with
`azd env set <KEY> <VALUE>`, but `microsoft-foundry/.env`
will not be written for you.

Important knobs (full list in `infra/.env.sample`):

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEO4J_URI` | demo DB | Neo4j Bolt URI. |
| `NEO4J_DATABASE` | `companies` | Neo4j database. |
| `NEO4J_READ_ONLY` | `true` | Read-only MCP tools. Set `false` for writes. |
| `NEO4J_MCP_CONTAINER_IMAGE` | `mcp/neo4j:latest` | Pin a tested tag. |
| `MCP_EXTERNAL_INGRESS` | `true` | Public HTTPS. `false` makes it internal. |
| `MCP_MIN_REPLICAS` | `1` | Warm endpoint. Set `0` if cold starts are fine. |
| `FOUNDRY_MODEL_CAPACITY` | `120` | Chat-model TPM capacity for the Foundry deployment. |
| `FOUNDRY_EMBEDDING_MODEL_CAPACITY` | `30` | Embedding-model TPM capacity for vector search. |

## Authentication Model

In HTTP mode, the Neo4j MCP server is stateless and expects auth
on each request. It supports Basic auth and Bearer token pass-through:

```text
Authorization: Basic <base64(username:password)>
Authorization: Bearer <token>
```

Basic auth is the default for the `companies` demo graph and
direct Neo4j username/password access. Bearer token auth is for
Neo4j Enterprise or Aura deployments configured for SSO or OIDC;
the MCP server forwards the token to Neo4j and does not perform
OAuth itself.

For Foundry MCP tools, create a project connection that injects
the `Authorization` header. If you need OAuth client credentials,
user delegation, policy, or token exchange, put a gateway such as
Azure API Management in front of this server.

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

**`./deploy.sh` hangs.** Usually this is an auth issue. If `azd`
is in `az cli` auth mode and `az` is not logged in, `azd up`
can stall while waiting for a token refresh. Run `az login`
and try again.

**Foundry was provisioned but the smoke test or examples return 403.**
The Foundry User role assignment requires
`AZURE_PRINCIPAL_ID`. In `az cli` auth mode that value can be
empty, which causes the Bicep deployment to skip the role
assignment. Fix it with:

```bash
azd env set AZURE_PRINCIPAL_ID "$(az ad signed-in-user show --query id -o tsv)"
azd env set AZURE_PRINCIPAL_TYPE User
./deploy.sh
```

The next `./deploy.sh` re-runs `azd up` and adds the missing
role assignment.

**`azd up` fails with `DeploymentModelNotSupported` or a quota error.**
The default model `gpt-5-mini` (version `2025-08-07`) is broadly
available, but not in every region. Foundry agent APIs are supported
in `eastus`, `eastus2`, `swedencentral`, `westus`, `westus3`, and
others; Foundry hosted agents narrow that to Sweden Central, North
Central US, Canada Central, and Australia East. To switch models —
for example to the faster/cheaper non-reasoning `gpt-4.1-mini`, or to a
newer `gpt-5.4-mini` — set overrides before running `./deploy.sh`:

```bash
azd env set FOUNDRY_MODEL_NAME gpt-4.1-mini
azd env set FOUNDRY_MODEL_VERSION 2025-04-14
./deploy.sh
```

## Tear Down

```bash
azd down --force --purge
```

Deletes the resource group and everything in it. `--force` skips
the confirmation prompt. `--purge` empties the Log Analytics
workspace soft-delete bucket so the same environment name can be
redeployed cleanly. Expect 3-5 minutes for Container Apps to drain.

To reset the local azd state as well, remove `.azure`:

```bash
rm -rf .azure
```

## References

- [Azure Developer CLI environment variables](https://learn.microsoft.com/azure/developer/azure-developer-cli/manage-environment-variables)
- [Azure resource abbreviations](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/azure-best-practices/resource-abbreviations)
- [Subscription-scoped Bicep deployments](https://learn.microsoft.com/azure/azure-resource-manager/bicep/deploy-to-subscription)
