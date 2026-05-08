#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

endpoint="${1:-${NEO4J_MCP_ENDPOINT:-}}"

if [ -z "$endpoint" ]; then
  echo "Usage: ./test-mcp.sh https://<container-app-fqdn>/mcp"
  exit 1
fi

: "${NEO4J_USERNAME:=companies}"
: "${NEO4J_PASSWORD:=companies}"

auth_header="Authorization: Basic $(printf '%s:%s' "$NEO4J_USERNAME" "$NEO4J_PASSWORD" | base64 | tr -d '\n')"

curl --fail-with-body -sS "$endpoint" \
  -H "$auth_header" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
