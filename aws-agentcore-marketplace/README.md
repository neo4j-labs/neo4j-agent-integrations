# AWS Marketplace: Neo4j MCP on AgentCore (CLI Deployment)

## Introduction

This guide shows how to deploy the [Neo4j MCP server from AWS Marketplace](https://aws.amazon.com/marketplace) to Amazon Bedrock AgentCore using the AWS CLI.
A single shell script creates the required IAM role and AgentCore runtime - no CDK or infrastructure-as-code required.

**Key Features:**

- **AWS Marketplace Image**: Uses the official Neo4j MCP container published to AWS Marketplace
- **CLI-Only Deployment**: Single `deploy.sh` script - no CDK, CloudFormation, or Docker builds
- **IAM Authentication**: Secure, public runtime access via AWS IAM
- **Header-Based Neo4j Auth**: Neo4j credentials passed per-request via a custom authorization header

**Use Cases:**

- Quick proof-of-concept deployment with minimal setup
- Environments where CDK or CloudFormation is not available
- Exploring Neo4j MCP capabilities before committing to infrastructure-as-code

> For CDK-based deployment, see [Sample 1: MCP Runtime - Docker](../aws-agentcore/samples/1-mcp-runtime-docker/).

## Architecture Design

### Components

1. **AWS AgentCore Runtime**
   - Managed agent execution environment
   - Runs the Neo4j MCP container from AWS Marketplace
   - Public network mode with IAM authentication

2. **Neo4j MCP Container (AWS Marketplace)**
   - Official Neo4j MCP server image: `709825985650.dkr.ecr.us-east-1.amazonaws.com/neo4j/mcp:v0.1.7`
   - Stateless HTTP MCP server on port 8000
   - Provides MCP tools for schema inspection, Cypher execution, and graph exploration

3. **IAM Role**
   - Trust policy for `bedrock-agentcore.amazonaws.com`
   - Permissions for ECR image pull, CloudWatch Logs, X-Ray, and CloudWatch Metrics

4. **Custom Authorization Header**
   - `X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization` header
   - Neo4j credentials forwarded per-request from the invoking agent
   - No credentials stored in the container environment

5. **Neo4j Database**
   - Any reachable Neo4j instance (Aura, Desktop, or self-managed)
   - Default demo: `neo4j+s://demo.neo4jlabs.com:7687` (companies database)

## In-Depth Analysis

### Authentication Flow

```
User/Agent Request
    |
[AWS IAM Authentication + Neo4j credentials via X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization header]
    |
AgentCore Runtime (Public)
    |
Neo4j MCP Server (HTTP mode)
    |
[Extract Basic Auth from custom header]
    |
Neo4j Database
```

**Security Layers:**

1. **IAM Authentication**: Controls who can invoke the runtime
2. **Public Runtime**: Accessible via IAM, no VPC required
3. **Per-Request Auth**: Neo4j credentials passed as `Basic <base64(user:password)>` via the custom header
4. **TLS Encryption**: Secure connection to Neo4j via `neo4j+s://`

### Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `NEO4J_URI` | Yes | - | Neo4j connection URI |
| `NEO4J_DATABASE` | No | `neo4j` | Target database name |
| `NEO4J_READ_ONLY` | No | `true` | Restrict to read-only operations |
| `NEO4J_HTTP_AUTH_HEADER_NAME` | No | - | Custom header for Neo4j credentials |
| `NEO4J_HTTP_ALLOW_UNAUTHENTICATED_PING` | No | `true` | Allow unauthenticated health checks |
| `NEO4J_LOG_LEVEL` | No | `info` | Log verbosity |
| `NEO4J_LOG_FORMAT` | No | `text` | Log format (`text` or `json`) |

### MCP Tools Available

| Tool | Read-Only | Purpose |
|------|-----------|---------|
| `get-schema` | Yes | Introspects labels, relationship types, and property keys |
| `read-cypher` | Yes | Executes read-only Cypher queries |
| `write-cypher` | No | Executes write Cypher queries (when write access is enabled) |
| `list-gds-procedures` | Yes | Lists Graph Data Science procedures available |

For the full tool reference, see the [official Neo4j MCP server documentation](https://github.com/neo4j/mcp/?tab=readme-ov-file#tools--usage).

## How to Use This Example

### Prerequisites

- AWS Account with Bedrock and AgentCore access
- AWS CLI configured with appropriate credentials
- A running Neo4j database (or use the public demo database)

### Step 1: Configure

Edit the configuration variables at the top of [deploy.sh](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/aws-agentcore-marketplace/deploy.sh):

```bash
REGION="us-east-1"
RUNTIME_NAME="neo4j_mcp"
CONTAINER_URI="709825985650.dkr.ecr.us-east-1.amazonaws.com/neo4j/mcp:v0.1.7"

NEO4J_URI="neo4j+s://demo.neo4jlabs.com:7687"
NEO4J_DATABASE="companies"
NEO4J_READ_ONLY="true"
```

The defaults point to the public Neo4j companies demo database. Replace `NEO4J_URI` and `NEO4J_DATABASE` to use your own instance.

### Step 2: Deploy

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Create an IAM role (`Neo4jMCPRole`) with the required trust policy and permissions
2. Create an AgentCore runtime using the marketplace container image
3. Print the `AgentRuntimeId` for use in subsequent steps

### Step 3: Check Runtime Status

```bash
aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id <AGENT_RUNTIME_ID>
```

Wait until the runtime status is `ACTIVE` before invoking it.

### Step 4: Test the Runtime

Install the Python client dependencies:

```bash
pip install mcp-proxy-for-aws strands-agents boto3
```

Connect and invoke tools:

```python
from urllib.parse import quote
from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient
import base64
import boto3

arn = "<AGENT_RUNTIME_ARN>"
neo4j_user = "companies"
neo4j_password = "companies"

ENCODED_ARN = quote(arn, safe="")
credentials = base64.b64encode(f"{neo4j_user}:{neo4j_password}".encode()).decode()
region = boto3.Session().region_name

mcp_client = MCPClient(lambda: aws_iam_streamablehttp_client(
    endpoint=f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{ENCODED_ARN}/invocations?qualifier=DEFAULT",
    aws_region=region,
    aws_service="bedrock-agentcore",
    headers={
        "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization": f"Basic {credentials}",
    },
))
mcp_client.start()

# List available tools
result = mcp_client.list_tools_sync()
for t in result:
    print(f"- {t.tool_name}: {t.tool_spec.get('description')}")

# Get schema
result = mcp_client.call_tool_sync("1", "get-schema")
print(result)

# Run a Cypher query
result = mcp_client.call_tool_sync(
    "2",
    "read-cypher",
    tool_input={"query": "MATCH (n) RETURN labels(n) AS labels, count(*) AS count ORDER BY count DESC LIMIT 10"},
)
print(result)
```

### Step 5: Clean Up

```bash
# Delete the AgentCore runtime
aws bedrock-agentcore-control delete-agent-runtime \
  --agent-runtime-id <AGENT_RUNTIME_ID>

# Remove the IAM role policy and role (use the role name printed by deploy.sh)
aws iam delete-role-policy --role-name <ROLE_NAME> --policy-name Neo4jMCPRuntimePolicy
aws iam delete-role --role-name <ROLE_NAME>
```

### CDK Alternative

If you prefer infrastructure-as-code, [Sample 1: MCP Runtime - Docker](../aws-agentcore/samples/1-mcp-runtime-docker/) provides a full AWS CDK deployment.

## References

### AWS Documentation

- [AWS AgentCore Official Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AgentCore MCP Runtime Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [AWS Marketplace for AgentCore Runtimes](https://docs.aws.amazon.com/marketplace/latest/userguide/bedrock-agentcore-runtime.html)

### Neo4j Resources

- [Neo4j MCP Server (Canary)](https://github.com/neo4j-labs/neo4j-mcp-canary)
- [Neo4j MCP Support](https://github.com/neo4j-labs/neo4j-mcp-canary/issues)
