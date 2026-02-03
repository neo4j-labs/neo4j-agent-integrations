# AWS AgentCore + Neo4j Integration

Deploy Neo4j MCP servers and AI agents on Amazon Bedrock AgentCore.

## Overview

**Amazon Bedrock AgentCore** is AWS's framework-agnostic agent runtime and orchestration platform providing 8-hour execution windows, episodic memory, and comprehensive observability for production agent deployments.

This directory contains projects demonstrating end-to-end AgentCore integration with Neo4j:

| Directory | Description |
|-----------|-------------|
| [mcp-server/](./mcp-server/) | Deploy Neo4j MCP server to AgentCore Gateway with OAuth2 authentication |
| [agentcore-runtime/](./agentcore-runtime/) | Agents deployed to AgentCore Runtime (basic and orchestrator) |
| [standalone-agents/](./standalone-agents/) | Local Python scripts with OAuth2 token refresh and MCP testing |
| [sagemaker-samples/](./sagemaker-samples/) | Jupyter notebooks for SageMaker Studio with LangGraph and Strands |

## Quick Start

### 1. Deploy the MCP Server

First, deploy the Neo4j MCP server to AgentCore Gateway:

```bash
cd mcp-server
./deploy.sh
./deploy.sh credentials
```

See [mcp-server/README.md](./mcp-server/README.md) for detailed instructions.

### 2. Run an Agent

**Option A: Deploy to AgentCore Runtime**

```bash
cd agentcore-runtime/basic-agent
./agent.sh setup
./agent.sh deploy
./agent.sh invoke-cloud "What is the database schema?"
```

See [agentcore-runtime/README.md](./agentcore-runtime/README.md) for deployment options.

**Option B: Run locally with standalone scripts**

```bash
cd standalone-agents
python oauth2_mcp_agent.py "What is the database schema?"
```

See [standalone-agents/README.md](./standalone-agents/README.md) for local testing.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   AI Agent  │────▶│  AgentCore  │────▶│  AgentCore  │────▶│  Neo4j MCP  │
│  (Claude)   │     │   Gateway   │     │   Runtime   │     │   Server    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                   │
                                                                   ▼
                                                            ┌─────────────┐
                                                            │  Neo4j Aura │
                                                            │  Database   │
                                                            └─────────────┘
```

## Additional Resources

- [AGENTCORE_BEDROCK_INTEGRATION_GUIDE.md](./AGENTCORE_BEDROCK_INTEGRATION_GUIDE.md) - Conceptual overview of AWS AgentCore Bedrock integration patterns and manual integration approaches
- [Amazon Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io/)
