#!/usr/bin/env bash
# Register the official Neo4j MCP server (neo4j-mcp-server) as a local (stdio)
# toolkit. Orchestrate installs and runs it; credentials come from the
# connection as NEO4J_MCP_* environment variables.
set -euo pipefail
source "$(dirname "$0")/../.env"

orchestrate toolkits add \
  --kind mcp \
  --name "$MCP_TOOLKIT_NAME" \
  --description "Neo4j companies knowledge graph: schema inspection and read-only Cypher" \
  --command "uvx --from neo4j-mcp-server python -m neo4j_mcp_server" \
  --tools "*" \
  --app-id "$CONNECTION_APP_ID"

orchestrate toolkits list
orchestrate tools list