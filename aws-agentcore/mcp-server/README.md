# Neo4j MCP Server on Amazon Bedrock AgentCore

Deploy the Neo4j MCP server to Amazon Bedrock AgentCore with Gateway access for AI agents.

> **Primary Goal:** This project is a **prototype for learning AWS AgentCore Gateway**. The Gateway is a critical component that provides unified authentication, centralized access control, multi-target aggregation, and audit logging. The Gateway architecture must not be removed or bypassed.

## Overview

This project deploys the [Neo4j MCP server](https://github.com/neo4j/mcp) to AWS via AgentCore Gateway, enabling LLM agents to query Neo4j databases using the Model Context Protocol (MCP). Access is restricted to machine-to-machine (M2M) authentication only, designed specifically for agent access.

**Key Learning Objectives:**
- AgentCore Gateway configuration with OAuth2 authentication
- Gateway Target setup connecting Gateway to Runtime
- M2M (machine-to-machine) authentication via Cognito
- Gateway tool name prefixing and dynamic tool discovery
- Claude Sonnet integration via AWS Bedrock for MCP tool calling

**Architecture:**

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   AI Agent  │────▶│   Cognito   │────▶│  AgentCore  │────▶│  AgentCore  │────▶│  Neo4j MCP  │
│  (Claude)   │ M2M │  (OAuth2)   │ JWT │   Gateway   │OAuth│   Runtime   │     │   Server    │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
                                                                                       │
                                                                                       ▼
                                                                                ┌─────────────┐
                                                                                │  Neo4j Aura │
                                                                                │  Database   │
                                                                                └─────────────┘
```

**Key Features:**
- **Gateway-Only Access** - All requests go through AgentCore Gateway (no direct Runtime access)
- **M2M Authentication** - OAuth2 client credentials flow for agent access
- **No User Accounts** - No username/password management required
- **Automatic Token Exchange** - Gateway handles OAuth2 tokens with Runtime

**MCP Tools Available (Read-Only Mode):**
- `neo4j-mcp-server-target___get-schema` - Get the database schema
- `neo4j-mcp-server-target___read-cypher` - Execute read-only Cypher queries

> **Note:** Tool names are prefixed with the Gateway target name when accessed via Gateway. See [ARCHITECTURE.md](./ARCHITECTURE.md#gateway-tool-name-mapping) for details.

## Quick Start

### Prerequisites

- Docker with buildx support
- AWS CLI configured with appropriate credentials
- AWS CDK CLI (`npm install -g aws-cdk`)
- Python 3.10+
- Neo4j Aura database (or other Neo4j instance)

> **Important:** The Neo4j database must be running and accessible before deployment. The Neo4j MCP server verifies database connectivity on startup and exits immediately if it cannot connect. If using Neo4j Aura, ensure the database instance is resumed (not paused) before running `./deploy.sh`.

### 1. Configure Credentials

Edit the `.env` file in the parent directory:

```bash
# Neo4j Database (passed to container at deploy time)
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_DATABASE=neo4j
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-neo4j-password

# Stack Configuration
STACK_NAME=neo4j-agentcore-mcp-server
AWS_REGION=us-west-2
```

> **Note:** No AGENT_USERNAME/AGENT_PASSWORD needed. The stack uses M2M OAuth2 with automatically generated client credentials.

### 2. Deploy

```bash
./deploy.sh
```

This command:
1. Builds the ARM64 Docker image
2. Creates an ECR repository and pushes the image
3. Deploys the CDK stack with:
   - Cognito User Pool with OAuth2 Resource Server
   - Machine Client for M2M authentication
   - AgentCore Runtime with JWT authorizer
   - AgentCore Gateway with OAuth2 credential provider
   - Gateway Target connecting Gateway to Runtime
4. Creates custom resources for OAuth provider and runtime health check

Deployment takes approximately 5-10 minutes.

### 3. Generate Credentials

```bash
./deploy.sh credentials
```

This generates `.mcp-credentials.json` with:
- Gateway URL
- OAuth2 client credentials (client_id, client_secret)
- Pre-fetched JWT token (valid for ~1 hour)

### 4. Test via Gateway (Recommended)

```bash
./cloud.sh
```

This tests the MCP server **via AgentCore Gateway** using the Python MCP client library. It reads credentials from `.mcp-credentials.json` and performs:

- **Token validation** - Checks if JWT token is still valid
- **MCP initialize** - Establishes MCP protocol session
- **tools/list** - Discovers available tools (with Gateway prefixes)
- **get-schema** - Retrieves Neo4j database schema
- **read-cypher** - Executes a test Cypher query

Available commands:
```bash
./cloud.sh          # Run full test suite
./cloud.sh token    # Check token status and expiry
./cloud.sh tools    # List available MCP tools
./cloud.sh schema   # Get database schema only
./cloud.sh query    # Run a test query
```

> **Note:** If the token expires, run `./deploy.sh credentials` to refresh it.

### 5. Test Direct Runtime (Debugging)

```bash
./cloud-http.sh
```

This tests the MCP server **directly against AgentCore Runtime** (bypassing Gateway) using raw HTTP requests. Useful for debugging when Gateway tests fail, to isolate whether the issue is with Gateway or Runtime.

It performs:
1. **Retrieves client secret** from Cognito
2. **Gets M2M token** using client_credentials OAuth2 flow
3. **Sends raw JSON-RPC** initialize request to Runtime endpoint
4. **Sends tools/list** JSON-RPC request

This script shows the underlying protocol that the MCP client library abstracts away.

### 6. Run a Sample Agent

**Option A: Deploy to AgentCore Runtime**
See [agentcore-runtime/README.md](../agentcore-runtime/README.md) for deploying agents to AgentCore.

**Option B: Run locally**
See [standalone-agents/README.md](../standalone-agents/README.md) for local Python scripts.

### 7. Cleanup

```bash
./deploy.sh cleanup
```

Removes all AWS resources.

## Commands

### deploy.sh

| Command | Description |
|---------|-------------|
| `./deploy.sh` | Full deployment (build, push, stack) |
| `./deploy.sh build` | Build ARM64 image only |
| `./deploy.sh push` | Push to ECR only |
| `./deploy.sh stack` | Deploy CDK stack only |
| `./deploy.sh synth` | Synthesize and preview the generated template |
| `./deploy.sh status` | Show stack status and outputs |
| `./deploy.sh credentials` | Generate `.mcp-credentials.json` with Gateway URL and JWT token |
| `./deploy.sh cleanup` | Delete stack and ECR repository |

### cloud.sh (Gateway Testing)

Uses `.mcp-credentials.json` generated by `./deploy.sh credentials`.

| Command | Description |
|---------|-------------|
| `./cloud.sh` | Run full test suite via Gateway |
| `./cloud.sh token` | Show current token and expiry status |
| `./cloud.sh tools` | List available MCP tools |
| `./cloud.sh schema` | Get database schema |
| `./cloud.sh query` | Run a test query |

### local.sh (Local Testing)

| Command | Description |
|---------|-------------|
| `./local.sh start` | Start local Docker server (no auth) |
| `./local.sh stop` | Stop local server |
| `./local.sh test` | Test local server |
| `./local.sh tools` | List tools on local server |

### cloud-http.sh (Direct Runtime Debugging)

Tests Runtime directly with raw HTTP, bypassing Gateway. Useful for debugging.

| Command | Description |
|---------|-------------|
| `./cloud-http.sh` | Run JSON-RPC tests against Runtime endpoint |

### Related: Sample Agents

- [agentcore-runtime/](../agentcore-runtime/) - Agents deployed to AgentCore Runtime
- [standalone-agents/](../standalone-agents/) - Local Python scripts for testing

## Configuration

All configuration is read from `../.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `NEO4J_URI` | Yes | Neo4j connection string |
| `NEO4J_DATABASE` | Yes | Database name |
| `NEO4J_USERNAME` | Yes | Neo4j username (passed to container) |
| `NEO4J_PASSWORD` | Yes | Neo4j password (passed to container) |
| `AWS_REGION` | No | AWS region (default: us-west-2) |
| `STACK_NAME` | No | CDK stack name (default: neo4j-agentcore-mcp-server) |

## Authentication

This deployment uses **M2M-only OAuth2 authentication** - there are no user accounts:

| Layer | Purpose | How It Works |
|-------|---------|--------------|
| Cognito OAuth2 | M2M Token | Client credentials flow with machine client |
| Gateway JWT | Gateway Access | Bearer token validates against Cognito |
| OAuth2 Provider | Gateway→Runtime | Gateway exchanges credentials for Runtime access |
| Neo4j (Env) | Database Access | Credentials configured at container startup |

**Authentication Flow:**

```
Agent → Cognito (client_credentials) → JWT Token
Agent → Gateway + JWT → Gateway validates token
Gateway → OAuth Provider → Gets Runtime token
Gateway → Runtime + OAuth Token → MCP Request
Runtime → Neo4j (env credentials) → Query
```

**Key Simplification:** Agents only need the Cognito client ID and secret (retrieved automatically from AWS). No username/password management required.

## Project Structure

```
mcp-server/
├── cdk/                              # AWS CDK Python application
│   ├── app.py                        # CDK app entry point
│   ├── neo4j_mcp_stack.py            # Stack definition (all resources)
│   ├── resources/
│   │   ├── oauth_provider/           # Lambda for OAuth2 credential provider
│   │   └── runtime_health_check/     # Lambda for runtime health check
│   ├── cdk.json                      # CDK configuration
│   └── requirements.txt              # Python dependencies
├── client/
│   ├── gateway_client.py             # Gateway client (uses .mcp-credentials.json)
│   └── mcp_operations.py             # MCP operation helpers
├── deploy.sh                         # Deployment script
├── cloud.sh                          # Gateway testing (MCP client)
├── cloud-http.sh                     # Direct Runtime testing (raw HTTP)
├── local.sh                          # Local Docker testing
├── .mcp-credentials.json             # Generated credentials (gitignored)
└── README.md                         # This file
```

### Credentials File

The `.mcp-credentials.json` file (generated by `./deploy.sh credentials`) contains:

```json
{
  "gateway_url": "https://..../mcp",
  "token_url": "https://....amazoncognito.com/oauth2/token",
  "client_id": "...",
  "client_secret": "...",
  "scope": "neo4j-agentcore-mcp-server-mcp/invoke",
  "access_token": "eyJ...",
  "token_expires_at": "2024-01-15T12:00:00+00:00",
  "region": "us-west-2",
  "stack_name": "neo4j-agentcore-mcp-server"
}
```

This file is gitignored and contains secrets. Other MCP clients can use it to connect to the Gateway.

## Local Development

Test the MCP server locally before deploying:

```bash
# Start local server (no auth needed)
./local.sh start

# Test locally
./local.sh test

# Stop when done
./local.sh stop
```

## Further Reading

See [ARCHITECTURE.md](./ARCHITECTURE.md) for:
- Detailed architecture diagrams (Mermaid)
- CDK stack structure and module breakdown
- Authentication flow sequence diagrams
- Why M2M-only via Gateway
- Why AgentCore vs Fargate/Lambda
- Gateway tool name mapping challenges
- Troubleshooting guide

## Resources

- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
