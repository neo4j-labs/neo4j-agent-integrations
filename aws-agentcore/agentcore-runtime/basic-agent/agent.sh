#!/bin/bash
# Neo4j MCP Agent - AgentCore Runtime
#
# A ReAct agent that connects to the Neo4j MCP server via AgentCore Gateway
# and answers natural language questions using AWS Bedrock Claude.
#
# Deployed on Amazon Bedrock AgentCore Runtime.
#
# Usage:
#   ./agent.sh setup              Install dependencies
#   ./agent.sh start              Start agent locally (port 8080)
#   ./agent.sh test               Test local agent
#   ./agent.sh configure          Configure for AWS deployment
#   ./agent.sh deploy             Deploy to AgentCore Runtime
#   ./agent.sh status             Check deployment status
#   ./agent.sh invoke-cloud "prompt"  Invoke deployed agent
#   ./agent.sh destroy            Remove from AgentCore
#
# Prerequisites:
#   - .mcp-credentials.json (from Neo4j MCP server deployment)
#   - AWS credentials configured (for Bedrock access)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_usage() {
    echo "Neo4j MCP Agent - AgentCore Runtime"
    echo ""
    echo "A ReAct agent that queries Neo4j via AgentCore Gateway."
    echo ""
    echo "Usage:"
    echo "  ./agent.sh setup              Install dependencies"
    echo "  ./agent.sh start              Start agent locally (port 8080)"
    echo "  ./agent.sh stop               Stop local agent"
    echo "  ./agent.sh test               Test local agent with curl"
    echo "  ./agent.sh configure          Configure for AWS deployment"
    echo "  ./agent.sh deploy             Deploy to AgentCore Runtime"
    echo "  ./agent.sh status             Check deployment status"
    echo "  ./agent.sh invoke-cloud       Invoke deployed agent (default question)"
    echo "  ./agent.sh invoke-cloud \"prompt\"  Invoke with custom question"
    echo "  ./agent.sh load-test          Run load test (5s interval)"
    echo "  ./agent.sh load-test N        Run load test with custom interval"
    echo "  ./agent.sh destroy            Remove from AgentCore"
    echo "  ./agent.sh help               Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./agent.sh start"
    echo "  ./agent.sh test"
    echo "  ./agent.sh configure"
    echo "  ./agent.sh deploy"
    echo "  ./agent.sh invoke-cloud"
    echo "  ./agent.sh invoke-cloud \"What is the database schema?\""
    echo "  ./agent.sh load-test"
    echo "  ./agent.sh load-test 10"
    echo ""
    echo "Prerequisites:"
    echo "  1. AWS CLI configured with credentials"
    echo "  2. Bedrock Claude Sonnet model access enabled"
    echo "  3. .mcp-credentials.json with gateway_url and access_token"
}

# Ensure dependencies are installed
ensure_deps() {
    if [ ! -d ".venv" ]; then
        echo -e "${YELLOW}Installing dependencies (first run)...${NC}"
        uv sync
        echo ""
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
        echo "  1. Copy .mcp-credentials.json from your Neo4j MCP server deployment"
        echo "  2. Run './agent.sh start' to test locally"
        echo "  3. Run './agent.sh configure' to set up AWS deployment"
        ;;

    start)
        ensure_deps
        if [ ! -f ".mcp-credentials.json" ]; then
            echo -e "${RED}ERROR: .mcp-credentials.json not found${NC}"
            echo ""
            echo "Copy credentials from your Neo4j MCP server deployment:"
            echo "  cp ../../mcp-server/.mcp-credentials.json ."
            exit 1
        fi
        echo -e "${GREEN}Starting agent locally on port 8080 with OTEL instrumentation...${NC}"
        echo "Test with: curl -X POST http://localhost:8080/invocations -H 'Content-Type: application/json' -d '{\"prompt\": \"Hello\"}'"
        echo ""
        # Use opentelemetry-instrument for automatic tracing (ADOT)
        uv run opentelemetry-instrument python aircraft-agent.py
        ;;

    stop)
        echo -e "${YELLOW}Stopping local agent...${NC}"
        pkill -f "python aircraft-agent.py" 2>/dev/null || echo "No agent process found"
        echo -e "${GREEN}Stopped.${NC}"
        ;;

    test)
        echo -e "${GREEN}Testing local agent...${NC}"
        echo ""
        curl -s -X POST http://localhost:8080/invocations \
            -H "Content-Type: application/json" \
            -d '{"prompt": "What is the database schema?"}' | python -m json.tool
        ;;

    configure)
        ensure_deps
        echo -e "${GREEN}Configuring agent for AWS deployment...${NC}"
        echo ""
        uv run agentcore configure -e aircraft-agent.py
        echo ""
        echo -e "${GREEN}Configuration complete!${NC}"
        echo "Run './agent.sh deploy' to deploy to AgentCore Runtime"
        ;;

    deploy)
        ensure_deps
        echo -e "${GREEN}Deploying to AgentCore Runtime...${NC}"
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
            PROMPT="How many aircraft are in the database?"
            echo -e "${GREEN}Invoking deployed agent with default question...${NC}"
        else
            PROMPT="$2"
            echo -e "${GREEN}Invoking deployed agent...${NC}"
        fi
        echo "Prompt: $PROMPT"
        echo ""
        uv run agentcore invoke "{\"prompt\": \"$PROMPT\"}"
        ;;

    load-test)
        ensure_deps
        INTERVAL="${2:-5}"
        echo -e "${GREEN}Starting load test (${INTERVAL}s interval)...${NC}"
        echo "Press Ctrl+C to stop"
        echo ""
        uv run python invoke_agent.py load-test "$INTERVAL"
        ;;

    destroy)
        ensure_deps
        echo -e "${YELLOW}Removing agent from AgentCore Runtime...${NC}"
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
