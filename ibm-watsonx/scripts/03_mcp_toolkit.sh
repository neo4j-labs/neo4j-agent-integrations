#!/usr/bin/env bash
# Register the official Neo4j MCP server as a local (stdio) toolkit.
# Orchestrate installs and runs the server itself - no hosting required.
set -euo pipefail
source "$(dirname "$0")/../.env"

orchestrate toolkits add \
  --kind mcp \
  --name "$MCP_TOOLKIT_NAME" \
  --description "Neo4j companies knowledge graph: schema inspection and read-only Cypher" \
  --command "uvx mcp-neo4j-cypher" \
  --tools "*" \
  --app-id "$CONNECTION_APP_ID"

orchestrate toolkits list
orchestrate tools list
