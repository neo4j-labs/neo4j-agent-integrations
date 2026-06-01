#!/usr/bin/env bash
set -euo pipefail

# Default: provision Foundry alongside the Neo4j MCP server. Override with:
#   azd env set CREATE_FOUNDRY_PROJECT false
# before re-running ./deploy.sh.
existing="$(azd env get-value CREATE_FOUNDRY_PROJECT 2>/dev/null || true)"
case "$existing" in
  true|false) exit 0 ;;
esac
azd env set CREATE_FOUNDRY_PROJECT true
