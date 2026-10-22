#!/usr/bin/env bash
# Import, wire, and deploy the finance LangGraph agent in Orchestrate.
# Prerequisites: an active Orchestrate environment, and the neo4j_mcp_finance
# connection from create_mcp_connection.sh. The OpenAI key comes from .env.
# Safe to re-run: it updates the connection and re-imports the agent.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${OPENAI_API_KEY:?OPENAI_API_KEY is not set in .env}"

AGENT=finance_graph_agent
LLM_APP_ID=finance_llm_openai

if ! orchestrate connections list 2>/dev/null | grep "\b$LLM_APP_ID\b" >/dev/null; then
  orchestrate connections add --app-id "$LLM_APP_ID"
fi
for env in draft live; do
  orchestrate connections configure --app-id "$LLM_APP_ID" --environment "$env" \
    --kind api_key --type team
  orchestrate connections set-credentials --app-id "$LLM_APP_ID" --environment "$env" \
    --api-key "$OPENAI_API_KEY"
done

orchestrate agents import --package-root mcp-setup/finance-agent
orchestrate agents connect --name "$AGENT" \
  --app-id "$LLM_APP_ID" --app-id neo4j_mcp_finance
# Import creates a draft. The Chat agent picker lists deployed agents only.
orchestrate agents deploy --name "$AGENT"

echo "Agent $AGENT is imported, connected and deployed."
