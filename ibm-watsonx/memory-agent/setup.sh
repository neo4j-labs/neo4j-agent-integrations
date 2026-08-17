#!/usr/bin/env bash
# Deploy the memory agent and wire its connections.
# Prerequisites: an active Orchestrate environment (see ../scripts/01_env.sh).
#
# Required values:
#   NAMS_API_KEY       from https://memory.neo4jlabs.com/dashboard
#   NAMS_WORKSPACE_ID  the X-Workspace-Id for your NAMS workspace
#   OPENAI_API_KEY     an OpenAI API key for the agent's LLM
set -euo pipefail

: "${NAMS_API_KEY:?set NAMS_API_KEY}"
: "${NAMS_WORKSPACE_ID:?set NAMS_WORKSPACE_ID}"
: "${OPENAI_API_KEY:?set OPENAI_API_KEY}"

create_connection () {
  local app_id="$1" value="$2"
  orchestrate connections add --app-id "$app_id" || true
  for env in draft live; do
    orchestrate connections configure --app-id "$app_id" \
      --environment "$env" -t team -k api_key
    orchestrate connections set-credentials --app-id "$app_id" \
      --environment "$env" -k "$value"
  done
}

# Injected credential keys follow {app_id}_{credential_type}:
#   nams_api        -> nams_api_api_key
#   nams_workspace  -> nams_workspace_api_key
#   llm_openai      -> llm_openai_api_key
create_connection nams_api       "$NAMS_API_KEY"
create_connection nams_workspace "$NAMS_WORKSPACE_ID"
create_connection llm_openai     "$OPENAI_API_KEY"

orchestrate agents import --package-root .
orchestrate agents connect -n memory_agent \
  -a nams_api -a nams_workspace -a llm_openai

orchestrate agents list