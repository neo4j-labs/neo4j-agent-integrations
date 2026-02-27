# Sample 1: AWS AgentCore Runtime with Neo4j MCP Docker Extension

## Introduction

This sample demonstrates how to deploy an AWS AgentCore Runtime with a custom-built Neo4j MCP Docker image.
A local Dockerfile extends the Neo4j MCP server and configures it for HTTP transport, which is then pushed to ECR and
deployed via CDK as an AgentCore Runtime.

**Key Features:**

- **Custom Docker Build**: Builds and pushes a local Neo4j MCP Docker image via CDK ECR Assets
- **IAM Authentication**: Uses AWS IAM permissions for secure, public runtime access
- **Header-Based Authentication**: Neo4j-Credentials are provided securely via a custom `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization` header
- **Serverless Deployment**: Fully managed AgentCore runtime
- **CDK Infrastructure**: Complete infrastructure-as-code deployment — no manual CLI configuration required

**Use Cases:**

- Quick deployment of Neo4j MCP capabilities for rapid prototyping.
- Secure access to Neo4j knowledge graphs for AI agents
- Enterprise-grade authentication and authorization

## Architecture Design

![Architecture Diagram](generated-diagrams/sample1_architecture.png)

### Components

1. **AWS AgentCore Runtime**
   - Managed agent execution environment
   - Built-in episodic memory
   - Framework-agnostic orchestration

2. **Neo4j MCP Docker Image**
   - Official MCP server from [Docker Hub](https://hub.docker.com/mcp/server/neo4j/overview)
   - Extended in AgentCore Runtime
   - Provides MCP-Tools to query Neo4j

3. **Custom Authorization Header**
   - `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization` header
   - Dynamic credential injection
   - Per-request authentication
   - Secure header transmission

4. **IAM Role**
   - Public runtime access with IAM authentication
   - Fine-grained permission controls
   - Service-linked role for workload identity

5. **Neo4j Database**
   - Demo instance: `neo4j+s://demo.neo4jlabs.com:7687`
   - Companies database with organizations, people, locations

## In-Depth Analysis

### Docker Build Mechanism

The sample uses a local [docker/Dockerfile](docker/Dockerfile) that configures the Neo4j MCP server for HTTP transport and deploys it via CDK ECR Assets:

```dockerfile
FROM mcp/neo4j:latest

ENV NEO4J_MCP_HTTP_HOST=0.0.0.0
ENV NEO4J_MCP_HTTP_PORT=8000
ENV NEO4J_TRANSPORT_MODE=http

EXPOSE 8000
```

**How It Works:**

1. CDK builds the Docker image from `docker/Dockerfile` and pushes it to ECR
2. The `CfnRuntime` resource references the ECR image URI
3. AgentCore runs the container with environment variables injected at deployment time
4. MCP protocol communication is automatically configured over HTTP
5. IAM permissions control access to the runtime

**Benefits:**

- Full control over the MCP server image
- Environment variables set at deploy time via CDK
- No manual CLI configuration required — everything is infrastructure-as-code

### Authentication Flow

```
User/Agent Request
    ↓
[AWS IAM Authentication + Neo4j-Credentials via X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization header]
    ↓
AgentCore Runtime (Public)
    ↓
Neo4j MCP Server (Configured with URI/DB only)
    ↓
[Extract Basic Auth from X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization header]
    ↓
Neo4j Database
```

**Security Layers:**

1. **IAM Authentication**: Controls who can invoke the runtime
2. **Public Runtime**: Accessible via IAM, no VPC required
3. **MCP-Auth**: Neo4j-Credentials passed securely via `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization` header per invocation
4. **TLS Encryption**: Secure connection to Neo4j (neo4j+s://)

### MCP Tools Available

For tools available see the [official Neo4j MCP server documentation](https://github.com/neo4j/mcp/?tab=readme-ov-file#tools--usage)

### CDK Stack Components

The CDK deployment creates:

- **ECR Image Asset** — Docker image built from [docker/Dockerfile](docker/Dockerfile) and pushed to ECR
- **IAM Role** for AgentCore Runtime with Bedrock, ECR, CloudWatch Logs, X-Ray, and workload identity permissions
- **AgentCore `CfnRuntime`** — configured with MCP protocol, public network mode, IAM auth, and the custom header allowlist

### Environment Variables

The MCP Docker container is configured with the following environment variables:

- `NEO4J_URI` - Database connection URI (Required)
- `NEO4J_DATABASE` - Database name (Optional, default: neo4j)
- `NEO4J_READ_ONLY` - Set to `true` to restrict the MCP server to read-only operations
- `NEO4J_LOG_FORMAT` - Log format, e.g. `text` or `json`
- `NEO4J_HTTP_AUTH_HEADER_NAME` - Name of the HTTP header used to pass Basic Auth credentials (set to `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization`)
- `NEO4J_HTTP_ALLOW_UNAUTHENTICATED_PING` - Set to `true` to allow unauthenticated health check pings

**Authentication:**

Credentials (`NEO4J_USERNAME`, `NEO4J_PASSWORD`) are NOT stored in the container. Instead, they are provided dynamically via the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization` header as a Base64-encoded Basic Auth value (`Basic <base64(user:password)>`) on each MCP tool invocation.

## How to Use This Example

### Prerequisites

- AWS Account with Bedrock and AgentCore access
- AWS CLI configured with appropriate credentials
- AWS CDK installed (`npm install -g aws-cdk`)
- Python 3.9+

### Step 1: Clone the Repository

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/aws-agentcore/samples/1-mcp-runtime-docker
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment

Neo4j uri and databse are supplied via CDK context. Default values are provided in [cdk.json](cdk.json):

```json
{
  "context": {
    "neo4j_uri": "neo4j+s://demo.neo4jlabs.com:7687",
    "neo4j_database": "companies"
  }
}
```

The sample uses the public companies demo database by default. To use your own Neo4j instance, either edit the values in `cdk.json` or override them at deploy time:

```bash
cdk deploy Neo4jMCPRuntimeStack \
  -c neo4j_uri=neo4j+s://your-instance:7687 \
  -c neo4j_database=neo4j
```

### Step 4: Deploy Infrastructure

```bash
# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy the stack
cdk deploy Neo4jMCPRuntimeStack

# Confirm the deployment when prompted
```

**Expected Output:**
The deployment will output:

- `Neo4jMcpImageUri` — ECR URI of the built Docker image
- `Neo4jMcpRuntimeArn` — ARN of the deployed AgentCore Runtime
- `AgentRuntimeRoleArn` — ARN of the IAM Role for the runtime

The CDK stack automatically:
- Builds the Docker image from `docker/Dockerfile` and pushes it to ECR
- Creates the IAM role with the required permissions
- Creates and configures the `CfnRuntime` with MCP protocol, public access, and IAM auth

### Step 5: Test the Runtime

Open [demo.ipynb](demo.ipynb) and set the `arn` variable to the `Neo4jMcpRuntimeArn` from the CDK output, then run the notebook.
It uses `mcp_proxy_for_aws` and `strands` to connect via IAM-signed requests and the `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization`
header for Neo4j credentials.

```python
arn = "<Neo4jMcpRuntimeArn from CDK output>"
neo4j_user = "companies"
neo4j_password = "companies"
```

### Step 6: Clean Up

```bash
# Destroy the CDK stack (removes the Runtime, IAM role, and ECR image)
cdk destroy Neo4jMCPRuntimeStack
```

## References

### AWS Documentation

- [AWS AgentCore Official Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AgentCore MCP Runtime Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)

### Neo4j Resources

- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Neo4j MCP Docker Hub](https://hub.docker.com/mcp/server/neo4j/overview)
