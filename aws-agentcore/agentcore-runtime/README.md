# Neo4j MCP Agent - AgentCore Runtime

This project demonstrates how to build and deploy AI agents on **Amazon Bedrock AgentCore Runtime** that use the **Model Context Protocol (MCP)** to query a Neo4j graph database containing aviation fleet data.


## Agent Comparison

| Feature | Basic Agent | Orchestrator Agent |
|---------|-------------|-------------------|
| Architecture | Single ReAct loop | Router + 2 specialists |
| Observability | Basic traces | Rich multi-agent traces |
| Domain handling | Generic prompts | Specialized prompts per domain |
| Best for | Getting started | Production demos, observability |

## Domain Specialists (Orchestrator)

| Agent | Handles | Example Queries |
|-------|---------|-----------------|
| **Maintenance** | Faults, components, sensors, reliability | "Most common maintenance faults", "Hydraulic system issues" |
| **Operations** | Flights, delays, routes, airports | "Common delay causes", "Busiest routes" |

## Prerequisites

1. **Python 3.10+** and **uv** package manager
2. **AWS CLI** configured with credentials
3. **Bedrock Claude Sonnet model access** enabled in AWS console
4. **Deployed Neo4j MCP Server** with AgentCore Gateway (see [mcp-server](../mcp-server/))

## Key Technologies

- **Amazon Bedrock AgentCore** - Managed runtime for deploying and scaling AI agents
- **Model Context Protocol (MCP)** - Standard protocol for connecting LLMs to external tools and data sources
- **LangGraph** - Multi-agent orchestration with StateGraph and conditional routing
- **LangChain** - ReAct agent pattern and MCP tool adapters
- **Claude Sonnet 4** - LLM powering agent reasoning (via Bedrock Converse API)
- **OpenTelemetry** - Observability with AWS Distro for OpenTelemetry (ADOT)

## Overview

Two agent implementations are provided, progressing from simple to multi-agent orchestration:

| Agent | Description | Use Case |
|-------|-------------|----------|
| [basic-agent/](./basic-agent/) | Single ReAct agent | Simple queries, getting started |
| [orchestrator-agent/](./orchestrator-agent/) | Multi-agent with routing | Rich observability, domain specialization |

## Quick Start

### Option 1: Basic Agent (Single Agent)

A single ReAct agent that handles all queries:

```bash
cd basic-agent
./agent.sh setup          # Install dependencies
./agent.sh start          # Run locally (port 8080)
./agent.sh test           # Test local agent
./agent.sh deploy         # Deploy to AgentCore
./agent.sh invoke-cloud "What is the database schema?"
```

### Option 2: Orchestrator Agent (Multi-Agent)

Routes queries to specialized Maintenance or Operations agents:

```bash
cd orchestrator-agent
./agent.sh setup          # Install dependencies
./agent.sh start          # Run locally (port 8080)
./agent.sh test-maintenance   # Test routing to Maintenance Agent
./agent.sh test-operations    # Test routing to Operations Agent
./agent.sh deploy         # Deploy to AgentCore
./agent.sh load-test      # Continuous cloud testing with random queries
```

See [orchestrator-agent/README.md](./orchestrator-agent/README.md) for multi-agent architecture details.

### Option 3: Local Docker Testing

Test agents locally using Docker before deploying:

```bash
# Install dependencies (run from agentcore-runtime/)
uv sync

# Sync credentials from MCP server to agent directories
uv run local-test sync-credentials

# Build and test an agent (all-in-one)
uv run local-test all basic-agent

# Or step by step:
uv run local-test build basic-agent      # Build Docker image
uv run local-test run basic-agent        # Start container
uv run local-test test basic-agent       # Send test request
uv run local-test logs basic-agent       # View logs
uv run local-test stop basic-agent       # Stop container

# Check status of all containers
uv run local-test status
```

### Option 4: CloudFormation Deployment

Deploy to AgentCore using raw CloudFormation (no CDK):

```bash
cd cfn

# Deploy basic-agent
./deploy.sh basic-agent

# Deploy orchestrator-agent
./deploy.sh orchestrator-agent

# Custom stack name
./deploy.sh basic-agent my-custom-stack

# Cleanup
./cleanup.sh basic-agent
./cleanup.sh basic-agent my-custom-stack --delete-ecr
```

## References

**AgentCore:**
- [Bedrock AgentCore Starter Toolkit](https://aws.github.io/bedrock-agentcore-starter-toolkit/index.html)
- [AgentCore Runtime Quickstart](https://aws.github.io/bedrock-agentcore-starter-toolkit/user-guide/runtime/quickstart.html)
- [Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)

**MCP & Neo4j:**
- [mcp-server](../mcp-server/) - The MCP server this agent connects to
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [Model Context Protocol](https://modelcontextprotocol.io/)

**Multi-Agent:**
- [ORCHESTRATOR.md](./ORCHESTRATOR.md) - Design document for multi-agent architecture
- [LangGraph Multi-Agent](https://langchain-ai.github.io/langgraph/concepts/multi_agent/) - LangGraph multi-agent patterns
