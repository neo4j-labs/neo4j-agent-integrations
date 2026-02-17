# Sample 1: AWS AgentCore Runtime with Neo4j MCP Docker Extension

## Introduction

This sample demonstrates how to extend AWS AgentCore Runtime with a Neo4j MCP server using Docker container extension. AgentCore Runtime provides the ability to extend an existing Docker image, allowing you to package and deploy the official Neo4j MCP server as part of your agent runtime environment.

**Key Features:**

- **Docker Extension**: Extends the official Neo4j MCP Docker image from Docker Hub
- **IAM Authentication**: Uses AWS IAM permissions for secure, public runtime access
- **Header-Based Authentication**: Credentials provided securely via MCP-Auth header
- **Serverless Deployment**: Fully managed AgentCore runtime
- **CDK Infrastructure**: Complete infrastructure-as-code deployment

**Use Cases:**

- Quick deployment of Neo4j MCP capabilities for rapid prototyping. Please use [the Gateway example](2-gateway-external-mcp/README.md) for production deployments
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

3. **MCP-Auth Header**
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
   - Production-ready for custom Neo4j instances

## In-Depth Analysis

### Docker Extension Mechanism

AgentCore Runtime's Docker extension feature allows you to:

```bash
# Configure runtime with Docker image extension
agentcore configure -e docker://mcp/server/neo4j:latest --protocol MCP
```

**How It Works:**

1. AgentCore pulls the specified Docker image
2. Runtime environment is extended with the MCP server
3. Container runs within the AgentCore execution context
4. MCP protocol communication is automatically configured
5. IAM permissions control access to the runtime

**Benefits:**

- No custom server code required
- Leverage official, maintained MCP servers

### Authentication Flow

```
User/Agent Request
    ↓
[AWS IAM Authentication]
    ↓
AgentCore Runtime (Public)
    ↓
[Extended Docker Container]
    ↓
Neo4j MCP Server (Configured Only with URI/DB)
    ↓
[MCP-Auth Header - Credentials]
    ↓
Neo4j Database
```

**Security Layers:**

1. **IAM Authentication**: Controls who can invoke the runtime
2. **Public Runtime**: Accessible via IAM, no VPC required
3. **MCP-Auth**: Credentials passed securely via headers per invocation
4. **TLS Encryption**: Secure connection to Neo4j (neo4j+s://)

### MCP Tools Available

For tools available see the [official Neo4j MCP server documentation](https://github.com/neo4j/mcp/?tab=readme-ov-file#tools--usage)

### CDK Stack Components

The CDK deployment creates:

- **IAM Role** for AgentCore Runtime with Bedrock permissions
- **ECS Task Definition** configured with Neo4j environment variables

### Environment Variables

The MCP Docker container is configured with the following environment variables:

- `NEO4J_URI` - Database connection URI (Required)
- `NEO4J_DATABASE` - Database name (Optional, default: neo4j)

**Authentication:**

Credentials (`NEO4J_USERNAME`, `NEO4J_PASSWORD`) are NOT stored in the container. Instead, they are provided dynamically via the `MCP-Auth` header on each MCP tool invocation.

## How to Use This Example

### Prerequisites

- AWS Account with Bedrock and AgentCore access
- AWS CLI configured with appropriate credentials
- AWS CDK installed (`npm install -g aws-cdk`)
- Python 3.9+
- Access to Neo4j database (demo or production)

### Step 1: Clone the Repository

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/aws-agentcore/samples/1-mcp-runtime-docker
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

Configure the AgentCore Runtime with the following environment variables:

- `NEO4J_URI`: `neo4j+s://demo.neo4jlabs.com:7687`
- `NEO4J_DATABASE`: `companies`

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

- Runtime Role ARN for AgentCore
- Stack ARN

### Step 5: Configure AgentCore Runtime

```bash
# Configure the runtime with Neo4j MCP Docker image
agentcore configure \
  -e docker://mcp/server/neo4j:latest \
  --protocol MCP \
  --name neo4j-mcp-runtime \
  --role-arn <RuntimeRoleArn from CDK output>

# Set up IAM authentication (public runtime)
agentcore configure \
  --runtime-name neo4j-mcp-runtime \
  --auth-type IAM \
  --public-access true
```

**Expected Output:**
The configuration will show:

- Runtime ARN
- Status: ACTIVE
- MCP Protocol: Enabled
- Authentication: IAM
- Access: Public

### Step 6: Test the Runtime

**Using AWS CLI:**

Create a session and invoke tools using the AWS CLI with the runtime ARN and tool parameters.

**Using Python SDK:**

Use the boto3 `bedrock-agentcore` client to:

1. Create a session with the runtime ARN
2. Invoke tools like `query_graph` with Cypher queries
3. Process the returned graph data

### Step 7: Integrate with Bedrock Agents

Connect your Bedrock agents to the AgentCore Runtime to enable:

- Company data queries via Neo4j
- Graph relationship traversal
- Knowledge graph integration in agent workflows

The runtime handles:

- Tool orchestration
- MCP protocol communication
- Credential management
- Session state

### Step 8: Clean Up

```bash
# Destroy the CDK stack
cdk destroy Neo4jMCPRuntimeStack

# Delete the AgentCore runtime
agentcore delete-runtime --runtime-name neo4j-mcp-runtime
```

## References

### AWS Documentation

- [AWS AgentCore Official Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/agentcore.html)
- [AgentCore MCP Runtime Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)

- [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)

### Neo4j Resources

- [Neo4j MCP Server](https://github.com/neo4j/mcp)
- [Neo4j MCP Docker Hub](https://hub.docker.com/mcp/server/neo4j/overview)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/current/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/current/)

### Demo Database

- **URI**: `neo4j+s://demo.neo4jlabs.com:7687`
- **Username**: `companies`
- **Password**: `companies`
- **Database**: `companies`
- **Schema**: Organizations, People, Locations, Industries, Articles

### Related Samples

- [Sample 2: AgentCore Gateway with External Neo4j MCP](../2-gateway-external-mcp/README.md)
- [Sample 3: AgentCore Runtime with Neo4j SDK Tools](../3-runtime-neo4j-sdk/README.md)

### Community

- [Neo4j Agent Integrations Repository](https://github.com/neo4j-labs/neo4j-agent-integrations)
- [MCP Specification](https://modelcontextprotocol.io/)
