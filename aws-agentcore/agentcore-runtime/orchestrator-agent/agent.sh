#!/bin/bash
# Multi-Agent Orchestrator - AgentCore Runtime
#
# A supervisor agent that routes queries to specialized workers:
# - Maintenance Agent: reliability, faults, components, sensors
# - Operations Agent: flights, delays, routes, airports
#
# Usage:
#   ./agent.sh setup              Install dependencies
#   ./agent.sh start              Start orchestrator locally (port 8080)
#   ./agent.sh test               Test local orchestrator
#   ./agent.sh configure          Configure for AWS deployment
#   ./agent.sh deploy             Deploy to AgentCore Runtime
#   ./agent.sh status             Check deployment status
#   ./agent.sh invoke-cloud           Send default question to deployed agent
#   ./agent.sh invoke-cloud "prompt"  Send custom question to deployed agent
#   ./agent.sh destroy            Remove from AgentCore

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo "Multi-Agent Orchestrator - AgentCore Runtime"
    echo ""
    echo "Routes queries to Maintenance and Operations specialist agents."
    echo ""
    echo "Usage:"
    echo "  ./agent.sh setup              Install dependencies"
    echo "  ./agent.sh start              Start orchestrator locally (port 8080)"
    echo "  ./agent.sh stop               Stop local orchestrator"
    echo "  ./agent.sh test               Test local orchestrator"
    echo "  ./agent.sh test-maintenance   Test with maintenance query"
    echo "  ./agent.sh test-operations    Test with operations query"
    echo "  ./agent.sh configure          Configure for AWS deployment"
    echo "  ./agent.sh deploy             Deploy to AgentCore Runtime"
    echo "  ./agent.sh status             Check deployment status"
    echo "  ./agent.sh invoke-cloud       Send default question to deployed agent"
    echo "  ./agent.sh invoke-cloud \"q\"   Send custom question to deployed agent"
    echo "  ./agent.sh load-test          Cloud load test (random queries every 5s)"
    echo "  ./agent.sh load-test 10       Cloud load test with custom interval"
    echo "  ./agent.sh destroy            Remove from AgentCore"
    echo "  ./agent.sh help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./agent.sh test-maintenance   # Routes to Maintenance Agent"
    echo "  ./agent.sh test-operations    # Routes to Operations Agent"
    echo "  ./agent.sh invoke-cloud \"What are the most common faults?\""
    echo "  ./agent.sh load-test          # Continuous cloud load testing"
}

ensure_deps() {
    if [ ! -d ".venv" ]; then
        echo -e "${YELLOW}Installing dependencies (first run)...${NC}"
        uv sync
        echo ""
    fi
}

ensure_credentials() {
    if [ ! -f ".mcp-credentials.json" ]; then
        echo -e "${RED}ERROR: .mcp-credentials.json not found${NC}"
        echo ""
        echo "Copy credentials from basic-agent or MCP server deployment:"
        echo "  cp ../basic-agent/.mcp-credentials.json ."
        exit 1
    fi
}

case "${1:-help}" in
    setup)
        echo -e "${GREEN}Installing dependencies...${NC}"
        uv sync
        echo ""
        echo -e "${GREEN}Setup complete!${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Copy .mcp-credentials.json: cp ../basic-agent/.mcp-credentials.json ."
        echo "  2. Run './agent.sh start' to test locally"
        ;;

    start)
        ensure_deps
        ensure_credentials
        echo -e "${GREEN}Starting Multi-Agent Orchestrator on port 8080...${NC}"
        echo -e "${BLUE}Agents: Maintenance (faults/components) + Operations (flights/delays)${NC}"
        echo ""
        echo "Test with:"
        echo "  ./agent.sh test-maintenance   # Routes to Maintenance Agent"
        echo "  ./agent.sh test-operations    # Routes to Operations Agent"
        echo ""
        uv run opentelemetry-instrument python orchestrator_agent.py
        ;;

    stop)
        echo -e "${YELLOW}Stopping local orchestrator...${NC}"
        pkill -f "python orchestrator_agent.py" 2>/dev/null || echo "No orchestrator process found"
        echo -e "${GREEN}Stopped.${NC}"
        ;;

    test)
        echo -e "${GREEN}Testing orchestrator with general query...${NC}"
        echo ""
        curl -s -X POST http://localhost:8080/invocations \
            -H "Content-Type: application/json" \
            -d '{"prompt": "What is the database schema?"}' | python -m json.tool
        ;;

    test-maintenance)
        echo -e "${GREEN}Testing Maintenance Agent routing...${NC}"
        echo -e "${BLUE}Query: What are the most common maintenance faults?${NC}"
        echo ""
        curl -s -X POST http://localhost:8080/invocations \
            -H "Content-Type: application/json" \
            -d '{"prompt": "What are the most common maintenance faults?"}' | python -m json.tool
        ;;

    test-operations)
        echo -e "${GREEN}Testing Operations Agent routing...${NC}"
        echo -e "${BLUE}Query: What are the most common delay causes?${NC}"
        echo ""
        curl -s -X POST http://localhost:8080/invocations \
            -H "Content-Type: application/json" \
            -d '{"prompt": "What are the most common delay causes?"}' | python -m json.tool
        ;;

    configure)
        ensure_deps
        echo -e "${GREEN}Configuring orchestrator for AWS deployment...${NC}"
        echo ""
        uv run agentcore configure -e orchestrator_agent.py
        echo ""
        echo -e "${GREEN}Configuration complete!${NC}"
        echo "Run './agent.sh deploy' to deploy to AgentCore Runtime"
        ;;

    deploy)
        ensure_deps
        echo -e "${GREEN}Deploying Multi-Agent Orchestrator to AgentCore Runtime...${NC}"
        echo "This may take several minutes..."
        echo ""
        uv run agentcore deploy
        echo ""
        echo -e "${GREEN}Deployment complete!${NC}"
        echo "Run './agent.sh status' to check status"
        echo "Run './agent.sh invoke-cloud \"your question\"' to test"
        ;;

    status)
        ensure_deps
        echo -e "${GREEN}Checking deployment status...${NC}"
        echo ""
        uv run agentcore status
        ;;

    invoke|invoke-cloud)
        ensure_deps
        if [ -z "$2" ]; then
            PROMPT="What are the most common maintenance faults across all aircraft?"
            echo -e "${YELLOW}Using default question${NC}"
        else
            PROMPT="$2"
        fi
        echo -e "${GREEN}Invoking deployed orchestrator...${NC}"
        echo -e "${BLUE}Prompt: $PROMPT${NC}"
        echo ""
        uv run agentcore invoke "{\"prompt\": \"$PROMPT\"}"
        ;;

    load-test)
        ensure_deps
        echo -e "${GREEN}Starting cloud load test...${NC}"
        echo -e "${BLUE}Tests routing to Maintenance and Operations agents${NC}"
        echo ""
        if [ -n "$2" ]; then
            uv run python invoke_agent.py load-test --interval "$2"
        else
            uv run python invoke_agent.py load-test
        fi
        ;;

    destroy)
        ensure_deps
        echo -e "${YELLOW}Removing orchestrator from AgentCore Runtime...${NC}"
        echo ""
        uv run agentcore destroy
        echo ""
        echo -e "${GREEN}Cleanup complete!${NC}"
        ;;

    help|--help|-h)
        print_usage
        ;;

    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        print_usage
        exit 1
        ;;
esac
