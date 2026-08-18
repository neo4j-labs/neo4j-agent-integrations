#!/usr/bin/env bash
# Import the agent definition.
#
# KNOWN ISSUE (ADK 2.12.0): this fails with
#   "Toolkits are only supported for experimental_customer_care style agents"
# The identical agent can be created in the console. See docs/known-issues.md
# and docs/console-agent-setup.md.
set -euo pipefail
cd "$(dirname "$0")/.."

orchestrate agents import -f agents/neo4j_explorer.yaml
orchestrate agents list
