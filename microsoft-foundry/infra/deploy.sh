#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

command -v azd >/dev/null || {
  echo "Missing azd. Install: https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd"
  exit 1
}

shared_env="$(cd .. && pwd)/.env"

# Demo defaults (match .env.sample). Overridden below by the existing shared
# .env (if any) and then by this folder's local .env.
neo4j_uri="neo4j+s://demo.neo4jlabs.com:7687"
neo4j_database="companies"
neo4j_username="companies"
neo4j_password="companies"

foundry_resource_group=""
foundry_account_name=""
foundry_project_name=""
foundry_project_endpoint=""
foundry_model_deployment_name="gpt-4o-mini"
foundry_embedding_deployment_name="text-embedding-3-small"
neo4j_mcp_connection_name=""

read_kv_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  while IFS='=' read -r key value; do
    key="$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    value="$(echo "${value:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ -z "$key" ] || [[ "$key" == \#* ]]; then
      continue
    fi

    # Note: each `[ -n "$value" ] && var=...` returns 1 when value is empty,
    # which under `set -e` would silently kill the script. Each branch ends in
    # `|| :` so a missing/empty value is a no-op, not a script abort.
    case "$key" in
      NEO4J_URI)                     [ -n "$value" ] && neo4j_uri="$value"                          || : ;;
      NEO4J_DATABASE)                [ -n "$value" ] && neo4j_database="$value"                     || : ;;
      NEO4J_USERNAME)                [ -n "$value" ] && neo4j_username="$value"                     || : ;;
      NEO4J_PASSWORD)                [ -n "$value" ] && neo4j_password="$value"                     || : ;;
      FOUNDRY_RESOURCE_GROUP)        [ -n "$value" ] && foundry_resource_group="$value"             || : ;;
      FOUNDRY_ACCOUNT_NAME)          [ -n "$value" ] && foundry_account_name="$value"               || : ;;
      FOUNDRY_PROJECT_NAME)          [ -n "$value" ] && foundry_project_name="$value"               || : ;;
      FOUNDRY_PROJECT_ENDPOINT)      [ -n "$value" ] && foundry_project_endpoint="$value"           || : ;;
      FOUNDRY_MODEL_DEPLOYMENT_NAME)     [ -n "$value" ] && foundry_model_deployment_name="$value"      || : ;;
      FOUNDRY_EMBEDDING_DEPLOYMENT_NAME) [ -n "$value" ] && foundry_embedding_deployment_name="$value" || : ;;
      NEO4J_MCP_CONNECTION_NAME)         [ -n "$value" ] && neo4j_mcp_connection_name="$value"          || : ;;
    esac
  done < "$file"
}

# Order: existing shared .env, then local infra .env (wins for any key it sets).
read_kv_file "$shared_env"
read_kv_file ".env"

# Forward local infra .env values into the azd environment so deployment
# parameters reach the Bicep. azd up itself prompts for AZURE_ENV_NAME, the
# subscription, and AZURE_LOCATION.
if [ -f ".env" ]; then
  while IFS='=' read -r key value; do
    key="$(echo "$key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    value="$(echo "${value:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [ -z "$key" ] || [[ "$key" == \#* ]] || [ -z "$value" ]; then
      continue
    fi
    azd env set "$key" "$value" >/dev/null
  done < ".env"
fi

# Helper for safely reading values back out of the azd env after deploy.
azd_get() {
  local out
  if out="$(azd env get-value "$1" 2>/dev/null)" && [[ "$out" != ERROR:* ]]; then
    printf '%s' "$out"
  fi
}

# Default AZURE_LOCATION to swedencentral if not already set. Sweden Central is
# the only region in our supported list that ALSO supports Foundry hosted
# agents (Australia East / Canada Central / North Central US / Sweden Central),
# so deploying here means the same Foundry project can later host the
# agent-framework foundry-hosted example. Override with `azd env set
# AZURE_LOCATION ...` before re-running deploy.sh, or pick interactively the
# first time `azd up` prompts.
if [ -z "$(azd_get AZURE_LOCATION)" ]; then
  azd env set AZURE_LOCATION swedencentral >/dev/null
fi

# The `azure.ai.agents` azd extension's postdeploy hook reads AZURE_TENANT_ID
# from the azd env. azd doesn't auto-stamp it, so derive it from `az account
# show` (or an existing infra .env) and seed it before `azd up`.
seed_tenant_id="$(azd_get AZURE_TENANT_ID)"
if [ -z "$seed_tenant_id" ] && command -v az >/dev/null; then
  seed_sub="$(azd_get AZURE_SUBSCRIPTION_ID)"
  [ -z "$seed_sub" ] && seed_sub="$(az account show --query id -o tsv 2>/dev/null || true)"
  if [ -n "$seed_sub" ]; then
    seed_tenant_id="$(az account show --subscription "$seed_sub" --query tenantId -o tsv 2>/dev/null || true)"
    [ -n "$seed_tenant_id" ] && azd env set AZURE_TENANT_ID "$seed_tenant_id" >/dev/null
  fi
fi

# The Foundry opt-in prompt runs as an azd preprovision hook
# (hooks/preprovision.sh) so it happens after azd has created the env.
# Don't `set -e` exit on a non-zero `azd up` — even when post-deploy hooks fail
# (e.g. the azure.ai.agents extension), the Bicep outputs are still in the
# azd env and we can still stamp the shared .env. Capture status to report.
azd_up_status=0
azd up "$@" || azd_up_status=$?

# Read deployed values back from the azd env. Empty when Foundry was disabled.
endpoint="$(azd_get mcpEndpoint)"
foundry_rg_out="$(azd_get foundryResourceGroup)"
foundry_account_out="$(azd_get foundryAccountName)"
foundry_project_out="$(azd_get foundryProjectName)"
foundry_project_endpoint_out="$(azd_get foundryProjectEndpoint)"
foundry_model_out="$(azd_get foundryModelDeploymentName)"
foundry_embedding_out="$(azd_get foundryEmbeddingDeploymentName)"
azure_subscription_id="$(azd_get AZURE_SUBSCRIPTION_ID)"
azure_tenant_id="$(azd_get AZURE_TENANT_ID)"
if command -v az >/dev/null; then
  [ -z "$azure_subscription_id" ] && azure_subscription_id="$(az account show --query id -o tsv 2>/dev/null || true)"
  if [ -z "$azure_tenant_id" ] && [ -n "$azure_subscription_id" ]; then
    azure_tenant_id="$(az account show --subscription "$azure_subscription_id" --query tenantId -o tsv 2>/dev/null || true)"
  fi
fi

[ -n "$foundry_rg_out" ]               && foundry_resource_group="$foundry_rg_out"
[ -n "$foundry_account_out" ]          && foundry_account_name="$foundry_account_out"
[ -n "$foundry_project_out" ]          && foundry_project_name="$foundry_project_out"
[ -n "$foundry_project_endpoint_out" ] && foundry_project_endpoint="$foundry_project_endpoint_out"
[ -n "$foundry_model_out" ]            && foundry_model_deployment_name="$foundry_model_out"
[ -n "$foundry_embedding_out" ]        && foundry_embedding_deployment_name="$foundry_embedding_out"

# Write microsoft-foundry/.env so every example script in this section can
# source the same file.
cat > "$shared_env" <<EOF
# Auto-generated by microsoft-foundry/infra/deploy.sh.
# Re-run deploy.sh to refresh the deployed values; non-empty values you set
# here are preserved across runs.
#
# Examples authenticate to Foundry via 'az login' — AzureCliCredential
# pinned to AZURE_TENANT_ID below. No Foundry tokens or keys live here.

# Neo4j connection.
NEO4J_URI=${neo4j_uri}
NEO4J_DATABASE=${neo4j_database}
NEO4J_USERNAME=${neo4j_username}
NEO4J_PASSWORD=${neo4j_password}

# Neo4j MCP server (deployed).
NEO4J_MCP_ENDPOINT=${endpoint}

# Microsoft Foundry project. Auto-filled when deploy.sh provisions Foundry;
# blank if you opted out — set them yourself in that case to point examples
# at your existing Foundry project.
AZURE_SUBSCRIPTION_ID=${azure_subscription_id}
AZURE_TENANT_ID=${azure_tenant_id}
FOUNDRY_RESOURCE_GROUP=${foundry_resource_group}
FOUNDRY_ACCOUNT_NAME=${foundry_account_name}
FOUNDRY_PROJECT_NAME=${foundry_project_name}
FOUNDRY_PROJECT_ENDPOINT=${foundry_project_endpoint}
FOUNDRY_MODEL_DEPLOYMENT_NAME=${foundry_model_deployment_name}
FOUNDRY_EMBEDDING_DEPLOYMENT_NAME=${foundry_embedding_deployment_name}

# Neo4j MCP project connection name. Set this manually after creating the
# connection in the Foundry portal — see microsoft-foundry/examples/mcp/README.md.
NEO4J_MCP_CONNECTION_NAME=${neo4j_mcp_connection_name}
EOF

if [ "$azd_up_status" -eq 0 ]; then
  cat <<EOF

Neo4j MCP server is ready.

Endpoint:
  ${endpoint}

Shared environment file:
  ${shared_env}

Smoke test:
  ./test-mcp.sh "${endpoint}"

EOF
else
  cat <<EOF

azd up exited with status ${azd_up_status} — check the log above. The shared
.env was still refreshed from whatever values made it into the azd env, so
re-running may pick up where it left off.

Shared environment file:
  ${shared_env}

EOF
  exit "$azd_up_status"
fi
