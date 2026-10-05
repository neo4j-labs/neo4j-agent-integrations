#!/usr/bin/env bash
# Create the key_value connection holding Neo4j credentials.
# NEO4J_MCP_* keys are read by the official Neo4j MCP server (neo4j-mcp-server).
# NEO4J_* keys are read by the get_investments Python tool.
set -euo pipefail
source "$(dirname "$0")/../.env"

orchestrate connections add --app-id "$CONNECTION_APP_ID" || true

for env in draft live; do
  orchestrate connections configure --app-id "$CONNECTION_APP_ID" \
    --environment "$env" --kind key_value --type team

  orchestrate connections set-credentials --app-id "$CONNECTION_APP_ID" \
    --environment "$env" \
    -e "NEO4J_MCP_URI=$NEO4J_URI" \
    -e "NEO4J_MCP_USERNAME=$NEO4J_USERNAME" \
    -e "NEO4J_MCP_PASSWORD=$NEO4J_PASSWORD" \
    -e "NEO4J_MCP_DATABASE=$NEO4J_DATABASE" \
    -e "NEO4J_MCP_READ_ONLY=$NEO4J_READ_ONLY" \
    -e "NEO4J_MCP_TELEMETRY=false" \
    -e "NEO4J_URI=$NEO4J_URI" \
    -e "NEO4J_USERNAME=$NEO4J_USERNAME" \
    -e "NEO4J_PASSWORD=$NEO4J_PASSWORD" \
    -e "NEO4J_DATABASE=$NEO4J_DATABASE"
done

orchestrate connections list