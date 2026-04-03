# AWS Strands Agent with Neo4j MCP via AgentCore

## Introduction

This sample deploys an **AWS Strands Agent** as an AgentCore Runtime that connects to Neo4j via the AgentCore Gateway. The agent uses Cognito OAuth for MCP authentication and AgentCore Memory for user preference tracking.

> **Prerequisite:** This stack requires [Sample 2: Gateway with External Neo4j MCP](../aws-agentcore/samples/2-gateway-external-mcp) to be deployed first. The Gateway stack provides the Cognito OAuth setup and MCP Gateway endpoint that this agent connects to.

**Key Features:**

- **Strands Agent Framework**: Model-agnostic agent with streaming responses
- **AgentCore Gateway MCP**: Connects to Neo4j MCP through the AgentCore Gateway (from Sample 2)
- **Cognito OAuth (M2M)**: Client credentials flow for secure MCP access
- **AgentCore Memory**: Built-in user preference memory with per-user namespaces
- **CDK Infrastructure**: Complete infrastructure-as-code deployment

## Architecture

```
User Request
    ↓
AgentCore Runtime (Strands Agent)
    ├─ Bedrock LLM (Claude / cross-region inference)
    ├─ AgentCore Memory (user preferences)
    └─ MCP Client → [OAuth token from Cognito]
                        ↓
                  AgentCore Gateway (from Sample 2)
                        ↓
                  Neo4j MCP Server
                        ↓
                  Neo4j Database
```

### Components

1. **AgentCore Runtime** — Runs the Strands agent code deployed from S3
2. **Strands Agent** — Orchestrates LLM calls, MCP tool use, and memory
3. **MCP Client** — Obtains Cognito OAuth tokens and calls the AgentCore Gateway
4. **AgentCore Memory** — Stores and retrieves user preferences across sessions
5. **Secrets Manager** — Stores Cognito client credentials securely

### CDK Context Parameters

| Context key              | Source                           | Description                                                                                                                                                                                      |
|--------------------------|----------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `cognito_client_id`      | Sample 2 stack output            | Cognito app client ID                                                                                                                                                                            |
| `cognito_client_secret`  | Sample 2 stack output            | Cognito app client secret                                                                                                                                                                        |
| `cognito_scope`          | Sample 2 stack output            | OAuth scope (e.g. `neo4j-mcp-gateway/invoke`)                                                                                                                                                    |
| `cognito_token_endpoint` | Sample 2 stack output            | Cognito token endpoint URL                                                                                                                                                                       |
| `gateway_url`            | Sample 2 stack output            | AgentCore Gateway MCP URL                                                                                                                                                                        |
| `model_id`               | Command-line argument or default | The model ID to use for inference (for available Ids see https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html), default is `global.anthropic.claude-sonnet-4-6`  |

## In-Depth Analysis

### Authentication Flow

The MCP client ([strands_agent/mcp_client/client.py](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/aws-strands-agents/strands_agent/mcp_client/client.py)) implements an OAuth 2.0 `client_credentials` flow with token caching:

```
Agent invocation
    ↓
MCP Client checks token cache
    ├─ Valid & >30 s until expiry → reuse
    └─ Missing / expiring:
         ├─ Load credentials from Secrets Manager (cached after first call)
         ├─ POST client_credentials grant to Cognito
         └─ Cache access_token
    ↓
httpx.AsyncClient with "Authorization: Bearer <token>"
    ↓
AgentCore Gateway (JWT validation → Interceptor swaps for Neo4j Basic Auth)
    ↓
Neo4j MCP Server
```

- Credentials come from **Secrets Manager** (`SECRET_ARN`) on AgentCore, with env-var fallback for local dev
- Uses `streamable_http_client` from the MCP SDK, wrapped in a Strands `MCPClient`

### Code Deployment

The agent is deployed as **Python source code** bundled to S3 (no container image):

1. CDK bundles `strands_agent/` using `uv pip install` (targeting `manylinux_2_17_aarch64` / Python 3.13)
2. The bundle is uploaded as a CDK S3 Asset
3. `CfnRuntime` references the S3 location with `entry_point=main.py` and `PYTHON_3_13` runtime
4. AgentCore downloads and runs the code at invocation time

### Agent Entrypoint

The handler in [strands_agent/main.py](https://github.com/neo4j-labs/neo4j-agent-integrations/blob/main/aws-strands-agents/strands_agent/main.py) uses `BedrockAgentCoreApp`:

- **`@app.entrypoint`** — Async handler receiving `payload` and `context`
- **Session ID** — From `context.session_id`, fallback to uuid
- **Actor ID** — Required in payload; namespaces memory records per user
- **Streaming** — `agent.stream_async()` yields text chunks to the caller

### Memory

AgentCore Memory with a **UserPreferenceMemoryStrategy**:

- **Namespace:** `/users/{actorId}/preferences/`
- **Retrieval:** Top 5 results, 0.5 relevance threshold
- **Custom tool:** `clear_preferences` lets users reset stored preferences

The `AgentCoreMemorySessionManager` saves conversations and retrieves preferences before each turn.

### Model

- **Model:** `global.anthropic.claude-sonnet-4-6` (cross-region inference profile)
- **Auth:** IAM via the runtime execution role

### CDK Stack Resources

- **S3 Asset** — Agent code + dependencies bundled via `uv`
- **Secrets Manager** — Cognito `client_id` / `client_secret`
- **IAM Role** — S3, Secrets Manager, Bedrock, AgentCore Memory, CloudWatch, X-Ray, workload identity
- **AgentCore Memory** — `CfnMemory` with user preference strategy
- **AgentCore Runtime** — `CfnRuntime` (code-based, HTTP protocol, public network)

### Environment Variables

| Variable                      | Description                                                                                                                                                                                     |
|-------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `SECRET_ARN`                  | Secrets Manager ARN for Cognito credentials                                                                                                                                                     |
| `BEDROCK_AGENTCORE_MEMORY_ID` | AgentCore Memory resource ID                                                                                                                                                                    |
| `GATEWAY_URL`                 | AgentCore Gateway MCP endpoint                                                                                                                                                                  |
| `COGNITO_SCOPE`               | OAuth scope for the Gateway                                                                                                                                                                     |
| `COGNITO_TOKEN_ENDPOINT`      | Cognito token endpoint URL                                                                                                                                                                      |
| `AWS_DEFAULT_REGION`          | AWS region (set explicitly for AgentCore)                                                                                                                                                       |
| `MODEL_ID`                    | The model ID to use for inference (for available Ids see https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html), default is `global.anthropic.claude-sonnet-4-6` |

### MCP Tools Available

See the [official Neo4j MCP server documentation](https://github.com/neo4j/mcp/?tab=readme-ov-file#tools--usage).

## How to Use This Example

### Prerequisites

- AWS Account with Bedrock and AgentCore access
- AWS CLI and CDK installed
- Python 3.9+
- [Sample 2: Gateway with External Neo4j MCP](../aws-agentcore/samples/2-gateway-external-mcp) deployed — you will need its stack outputs

### Step 1: Clone the Repository

```bash
git clone https://github.com/neo4j-labs/neo4j-agent-integrations.git
cd neo4j-agent-integrations/aws-strands-agents
```

### Step 2: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 3: Get Outputs from Sample 2

Retrieve the Cognito and Gateway values from the deployed Gateway stack:

```bash
STACK_NAME=Neo4jAgentCoreGatewayStack

GATEWAY_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='GatewayUrl'].OutputValue" \
  --output text)

COGNITO_CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoAppClientId'].OutputValue" \
  --output text)

COGNITO_TOKEN_ENDPOINT=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoTokenEndpoint'].OutputValue" \
  --output text)

COGNITO_SCOPE=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoScope'].OutputValue" \
  --output text)

COGNITO_USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='CognitoUserPoolId'].OutputValue" \
  --output text)

COGNITO_CLIENT_SECRET=$(aws cognito-idp describe-user-pool-client \
  --user-pool-id "$COGNITO_USER_POOL_ID" \
  --client-id "$COGNITO_CLIENT_ID" \
  --query "UserPoolClient.ClientSecret" \
  --output text)
```

### Step 4: Deploy Infrastructure

```bash
# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy the stack
cdk deploy Neo4jStrandsAgentStack \
  -c cognito_client_id="$COGNITO_CLIENT_ID" \
  -c cognito_client_secret="$COGNITO_CLIENT_SECRET" \
  -c cognito_scope="$COGNITO_SCOPE" \
  -c cognito_token_endpoint="$COGNITO_TOKEN_ENDPOINT" \
  -c gateway_url="$GATEWAY_URL" \
  -c model_id="global.anthropic.claude-sonnet-4-6"
```

**Stack Outputs:**

| Output                | Description                                      |
| --------------------- | ------------------------------------------------ |
| `AgentRuntimeArn`     | ARN of the deployed AgentCore Runtime             |
| `AgentRuntimeRoleArn` | ARN of the IAM Role for the runtime               |
| `CognitoSecretArn`    | ARN of the Cognito credentials secret             |
| `AgentCoreMemoryId`   | ID of the AgentCore Memory resource               |

### Step 5: Test the Agent

Open [demo.ipynb](demo.ipynb) and set the `arn` variable to the `AgentRuntimeArn` from the CDK output, then run the notebook.

### Step 6: Clean Up

```bash
cdk destroy Neo4jStrandsAgentStack
```

## References

### AWS Documentation

- [AWS Strands Agents SDK](https://github.com/aws-strands-agents/sdk-python)
- [AgentCore Runtime Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-mcp.html)
- [AgentCore Gateway Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-using-mcp.html)

### Neo4j Resources

- [Neo4j MCP Server](https://github.com/neo4j/mcp)
