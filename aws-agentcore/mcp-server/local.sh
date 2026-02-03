#!/bin/bash
# ==============================================================================
# LOCAL.SH - Neo4j MCP Server Local Development Script
# ==============================================================================
#
# PURPOSE:
#   Manages a local Neo4j MCP server running in Docker for development and
#   testing. This is a thin wrapper that sets up the Python environment and
#   delegates to client/mcp_local_client.py for all functionality.
#
# TARGET:
#   Local Docker container at http://localhost:8000/mcp
#
# AUTHENTICATION:
#   None required - server uses NEO4J_* credentials from environment variables
#
# COMMANDS:
#   start              Start the local MCP server (Docker container)
#   stop               Stop the local MCP server
#   test               Run the full MCP client test suite
#   tools              List available MCP tools
#   call <tool> <json> Call a specific tool with JSON arguments
#
# EXAMPLES:
#   ./local.sh start
#   ./local.sh test
#   ./local.sh tools
#   ./local.sh call get-schema '{}'
#   ./local.sh call read-cypher '{"query": "MATCH (n) RETURN count(n)"}'
#
# ENVIRONMENT:
#   MCP_SERVER_URL - Override server URL (default: http://localhost:8000/mcp)
#   NEO4J_URI      - Neo4j connection URI (from .env)
#   NEO4J_USERNAME - Neo4j username (from .env)
#   NEO4J_PASSWORD - Neo4j password (from .env)
#
# SEE ALSO:
#   ./cloud.sh      - Cloud AgentCore testing (Cognito auth)
#   ./cloud-http.sh - Raw HTTP debugging for cloud server
#
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Setup Python virtual environment if needed
setup_venv() {
    if [[ ! -d "$SCRIPT_DIR/.venv" ]]; then
        echo "INFO  Setting up Python virtual environment..."
        python3 -m venv "$SCRIPT_DIR/.venv"
        source "$SCRIPT_DIR/.venv/bin/activate"
        pip install --quiet --upgrade pip
        pip install --quiet mcp httpx
        echo "OK    Virtual environment ready"
        echo ""
    else
        source "$SCRIPT_DIR/.venv/bin/activate"
    fi
}

# Map empty command to 'help'
command="${1:-help}"
shift 2>/dev/null || true

# Help doesn't need venv
if [[ "$command" == "help" || "$command" == "--help" || "$command" == "-h" ]]; then
    python3 "$SCRIPT_DIR/client/mcp_local_client.py" help
    exit 0
fi

# Setup venv and run
setup_venv
python3 "$SCRIPT_DIR/client/mcp_local_client.py" "$command" "$@"
