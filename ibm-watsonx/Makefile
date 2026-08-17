.PHONY: help env connections mcp-toolkit custom-tool agent verify all clean

help:
	@echo "make all           - env + connections + toolkits + tool"
	@echo "make env           - register and activate the Orchestrate environment"
	@echo "make connections   - create the Neo4j key_value connection (draft + live)"
	@echo "make mcp-toolkit   - register the Neo4j MCP server as a local toolkit"
	@echo "make custom-tool   - import the get_investments Python tool"
	@echo "make agent         - import the agent (see docs/known-issues.md)"
	@echo "make verify        - list toolkits, tools, models and agents"
	@echo "make clean         - remove the connection, toolkit and tool"

env:
	./scripts/01_env.sh

connections:
	./scripts/02_connections.sh

mcp-toolkit:
	./scripts/03_mcp_toolkit.sh

custom-tool:
	./scripts/04_custom_tool.sh

agent:
	./scripts/05_agent.sh

all: env connections mcp-toolkit custom-tool
	@echo ""
	@echo "Setup complete. Create the agent in the console:"
	@echo "  docs/console-agent-setup.md"

verify:
	orchestrate toolkits list
	orchestrate tools list
	orchestrate models list
	orchestrate agents list

clean:
	-orchestrate tools remove -n get_investments
	-orchestrate toolkits remove -n neo4j_local_mcp
	-orchestrate connections remove --app-id neo4j_local_creds
