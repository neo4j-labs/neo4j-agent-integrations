# Sample 3: AWS AgentCore Runtime with Neo4j Python SDK (Code-Based Deployment)

## Introduction

This sample demonstrates how to deploy an AWS AgentCore Runtime with a custom MCP server built using [FastMCP](https://github.com/jlowin/fastmcp) and the [Neo4j Python driver](https://github.com/neo4j/neo4j-python-driver).
Instead of using a pre-built Docker image, the MCP server is written as a Python script, bundled with its dependencies via CDK, uploaded to S3, and deployed as a code-based AgentCore Runtime.

**Key Features:**

- **Code-Based Deployment**: Python MCP server deployed directly from source via S3 — no Docker image required
- **FastMCP Framework**: Lightweight MCP server built with FastMCP for streamable HTTP transport
- **Pydantic Models**: Typed response models for organizations, industry categories, and articles
- **Neo4j Python Driver**: Direct Neo4j connectivity using the official Python driver
- **Secrets Manager Integration**: Neo4j credentials stored securely in AWS Secrets Manager
- **IAM Authentication**: Uses AWS IAM permissions for secure, public runtime access
- **CDK Infrastructure**: Complete infrastructure-as-code deployment — no manual CLI configuration required

**Use Cases:**

- Custom MCP tool development with full control over server logic
- Secure access to Neo4j knowledge graphs for AI agents
- Rapid prototyping with Python-based MCP servers
- Enterprise-grade secret management for database credentials

## Architecture Design

![Architecture Diagram](generated-diagrams/sample3_architecture.png)

### Components

1. **AWS AgentCore Runtime**
   - Managed agent execution environment
   - Code-based deployment from S3
   - Python 3.13 runtime
   - Framework-agnostic orchestration

2. **Custom MCP Server ([mcp_app/mcp_server.py](mcp_app/mcp_server.py))**
   - Built with FastMCP
   - Streamable HTTP transport (stateless)
   - Pydantic models for typed tool responses (`Organization`, `IndustryCategory`, `Article`)
   - Neo4j Python driver for database access
   - Credentials loaded from Secrets Manager at startup

3. **AWS Secrets Manager**
   - Stores Neo4j connection credentials (`NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`)
   - Secret ARN passed to the runtime via environment variable
   - Credentials fetched at server startup

4. **S3 Code Asset**
   - CDK bundles `mcp_app/` with dependencies using [uv](https://github.com/astral-sh/uv) in a Docker build step
   - Resulting package uploaded to S3
   - AgentCore Runtime loads the code from S3 at deployment time

5. **IAM Role**
   - S3 access for code retrieval
   - Secrets Manager access for credential retrieval
   - CloudWatch Logs and X-Ray for observability
   - Workload identity for AgentCore

6. **Neo4j Database**
   - Demo instance: `neo4j+s://demo.neo4jlabs.com:7687`
   - Companies database with organizations, people, locations

## In-Depth Analysis

### Code-Based Deployment Mechanism

The sample uses a Python MCP server in [mcp_app/mcp_server.py](mcp_app/mcp_server.py) that is bundled with its dependencies and deployed to S3 via CDK:

**How It Works:**

1. CDK bundles `mcp_app/` using a Docker build step with `uv` to install dependencies (`fastmcp`, `boto3`, `neo4j`, `pydantic`) for `linux/aarch64`
2. The bundled package is uploaded to S3 as a CDK asset
3. The `CfnRuntime` resource references the S3 location with `PYTHON_3_13` runtime and `mcp_server.py` as the entry point
4. At startup, the MCP server loads Neo4j credentials from Secrets Manager using the `SECRET_ARN` environment variable
5. The FastMCP server runs on streamable HTTP transport

**Benefits:**

- Full control over MCP server logic and tools
- No Docker image management — pure Python deployment
- Dependencies resolved at build time via `uv`
- Credentials managed securely via Secrets Manager

### Authentication Flow

```
User/Agent Request
    ↓
[AWS IAM Authentication]
    ↓
AgentCore Runtime (Public)
    ↓
MCP Server (mcp_server.py)
    ↓
[Load credentials from Secrets Manager via SECRET_ARN]
    ↓
Neo4j Database
```

**Security Layers:**

1. **IAM Authentication**: Controls who can invoke the runtime
2. **Public Runtime**: Accessible via IAM, no VPC required
3. **Secrets Manager**: Neo4j credentials stored and retrieved securely
4. **TLS Encryption**: Secure connection to Neo4j (`neo4j+s://`)

### MCP Tools Available

The custom MCP server exposes the following tools:

- **`get_organizations(limit: int)`** — Returns up to `limit` organizations from the Neo4j database. Each organization includes properties such as `name`, `summary`, `revenue`, `nbrEmployees`, `isPublic`, `isDissolved`, and `motto`.
- **`get_industry_categories(limit: int)`** — Returns up to `limit` industry category names from the Neo4j database.
- **`get_articles_by_organization(name: str)`** — Returns articles that mention the given organization. Each article includes properties such as `title`, `author`, `date`, `sentiment`, `siteName`, and `summary`.

You can extend [mcp_app/mcp_server.py](mcp_app/mcp_server.py) with additional `@mcp.tool()` decorated functions to add more tools.

### CDK Stack Components

The CDK deployment ([neo4j_sdk_runtime/neo4j_sdk_runtime_stack.py](neo4j_sdk_runtime/neo4j_sdk_runtime_stack.py)) creates:

- **S3 Code Asset** — `mcp_app/` bundled with dependencies via `uv` and uploaded to S3
- **Secrets Manager Secret** — Stores Neo4j connection credentials, values sourced from CDK context (`cdk.json` or `-c` overrides)
- **IAM Role** — Permissions for S3 code access, Secrets Manager, CloudWatch Logs, X-Ray, CloudWatch Metrics, and workload identity
- **AgentCore `CfnRuntime`** — Code-based deployment with MCP protocol, public network mode, and IAM auth

### Environment Variables

The AgentCore Runtime is configured with:

- `SECRET_ARN` — ARN of the Secrets Manager secret containing Neo4j credentials
- `AWS_DEFAULT_REGION` — AWS region (set explicitly for AgentCore compatibility)

The Secrets Manager secret contains:

- `NEO4J_URI` — Database connection URI (Required)
- `NEO4J_USERNAME` — Neo4j username (Required)
- `NEO4J_PASSWORD` — Neo4j password (Required)
- `NEO4J_DATABASE` — Database name (Optional, default: `neo4j`)

## How to Use This Example

### Prerequisites

- AWS Account with Bedrock and AgentCore access
- AWS CLI configured with appropriate credentials
- AWS CDK installed (`npm install -g aws-cdk`)
- Python 3.9+

### Step 1: Clone the Repository

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/aws-agentcore/samples/3-mcp-runtime-neo4j-sdk
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Neo4j Credentials

Neo4j connection credentials are supplied via CDK context. Default values are provided in [cdk.json](cdk.json):

```json
{
  "context": {
    "neo4j_uri": "neo4j+s://demo.neo4jlabs.com:7687",
     "neo4j_database": "companies",
     "neo4j_username": "companies",
     "neo4j_password": "companies"
  }
}
```

The sample uses the public companies demo database by default. To use your own Neo4j instance, either edit the values in `cdk.json` or override them at deploy time:

```bash
cdk deploy Neo4jSdkRuntimeStack \
  -c neo4j_uri=neo4j+s://your-instance:7687 \
  -c neo4j_database=neo4j \
  -c neo4j_username=neo4j \
  -c neo4j_password=your-password
```

### Step 4: Deploy Infrastructure

```bash
# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy the stack
cdk deploy Neo4jSdkRuntimeStack

# Confirm the deployment when prompted
```

**Expected Output:**
The deployment will output:

- `McpAppS3Bucket` — S3 bucket containing the MCP app deployment package
- `McpAppS3Key` — S3 object key of the deployment package
- `Neo4jSdkRuntimeArn` — ARN of the deployed AgentCore Runtime
- `AgentRuntimeRoleArn` — ARN of the IAM Role for the runtime
- `Neo4jSecretArn` — ARN of the Secrets Manager secret

The CDK stack automatically:
- Bundles `mcp_app/` with dependencies and uploads to S3
- Creates the Secrets Manager secret with Neo4j credentials
- Creates the IAM role with the required permissions
- Creates and configures the `CfnRuntime` with MCP protocol, public access, and IAM auth

### Step 5: Test the Runtime

Open [demo.ipynb](demo.ipynb) and set the `arn` variable to the `Neo4jSdkRuntimeArn` from the CDK output, then run the notebook.
It uses `mcp_proxy_for_aws` and `strands` to connect via IAM-signed requests.

```python
arn = "<Neo4jSdkRuntimeArn from CDK output>"
```

### Step 6: Clean Up

```bash
# Destroy the CDK stack (removes the Runtime, IAM role, secret, and S3 assets)
cdk destroy Neo4jSdkRuntimeStack
```

## References

### AWS Documentation

- [AWS AgentCore Official Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AgentCore MCP Runtime Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)

### Neo4j Resources

- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)
- [FastMCP](https://github.com/jlowin/fastmcp)
