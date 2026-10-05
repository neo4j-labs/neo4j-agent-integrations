#!/usr/bin/env bash
# Import the agent definition.
# MCP tools are referenced individually as <toolkit>:<tool> under `tools:`.
# Using a `toolkits:` key instead fails with "Toolkits are only supported for
# experimental_customer_care style agents".
set -euo pipefail
cd "$(dirname "$0")/.."

orchestrate agents import -f agents/neo4j_explorer.yaml
orchestrate agents list