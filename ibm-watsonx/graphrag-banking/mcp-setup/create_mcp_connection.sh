#!/usr/bin/env bash
# Create the neo4j_mcp_finance connection for the Neo4j finance MCP gateway.
# Values come from .mcp-credentials.finance.json. The gateway is protected by a
# Cognito client credentials flow, so Orchestrate fetches and refreshes the
# token itself. The same values are set for draft (preview chat) and live
# (deployed agent). Safe to re-run: it updates the values in place.
set -euo pipefail
cd "$(dirname "$0")/.."

CREDS=.mcp-credentials.finance.json
APP_ID=neo4j_mcp_finance

[[ -f "$CREDS" ]] || { echo "$CREDS not found" >&2; exit 1; }

field() { jq -er --arg k "$1" '.[$k]' "$CREDS"; }

GATEWAY_URL=$(field gateway_url)
TOKEN_URL=$(field token_url)
CLIENT_ID=$(field client_id)
CLIENT_SECRET=$(field client_secret)
SCOPE=$(field scope)

if ! orchestrate connections list 2>/dev/null | grep "\b$APP_ID\b" >/dev/null; then
  orchestrate connections add --app-id "$APP_ID"
fi

for env in draft live; do
  orchestrate connections configure --app-id "$APP_ID" --environment "$env" \
    --kind oauth_auth_client_credentials_flow --type team --server-url "$GATEWAY_URL"
  orchestrate connections set-credentials --app-id "$APP_ID" --environment "$env" \
    --token-url "$TOKEN_URL" --grant-type client_credentials \
    --client-id "$CLIENT_ID" --client-secret "$CLIENT_SECRET" --scope "$SCOPE"
done

echo "Connection $APP_ID is set for draft and live."
