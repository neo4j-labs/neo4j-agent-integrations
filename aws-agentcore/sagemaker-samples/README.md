# SageMaker Studio Notebooks

Jupyter notebooks demonstrating Neo4j MCP integration with AWS Bedrock in SageMaker Studio.

## Notebooks

| Notebook | Description | Framework |
|----------|-------------|-----------|
| [minimal_langgraph_agent.ipynb](./minimal_langgraph_agent.ipynb) | Minimal LangGraph agent with simple tools (no Neo4j) | LangGraph |
| [neo4j_simple_mcp_agent.ipynb](./neo4j_simple_mcp_agent.ipynb) | LangGraph ReAct agent querying Neo4j via MCP Gateway | LangGraph + MCP |
| [neo4j_strands_mcp_agent.ipynb](./neo4j_strands_mcp_agent.ipynb) | Strands agent querying Neo4j via MCP Gateway | AWS Strands + MCP |

## Prerequisites

1. **SageMaker Studio** environment with Python 3.10+
2. **AWS Bedrock model access** enabled for Claude models
3. **Inference Profile** created using the setup script (see below)
4. **Deployed MCP Server** with AgentCore Gateway (for Neo4j notebooks)

## Setup

### 1. Create an Inference Profile

Before running any notebook, create an inference profile from the CLI:

```bash
# Fast & cheap - great for testing
./setup-inference-profile.sh haiku

# Balanced - recommended for production
./setup-inference-profile.sh sonnet

# Create and test
./setup-inference-profile.sh --test haiku
```

Copy the ARN output and paste it into the notebook's configuration cell.

### 2. For Neo4j Notebooks

Copy credentials from your deployed MCP server:
- `GATEWAY_URL` from `.mcp-credentials.json`
- `ACCESS_TOKEN` from `.mcp-credentials.json`

See [../mcp-server/](../mcp-server/) for deployment instructions.

## Notebook Details

### minimal_langgraph_agent.ipynb

A starting point for learning LangGraph with AWS Bedrock. Demonstrates:
- ChatBedrockConverse setup with inference profiles
- Simple tool definitions (get_current_time, add_numbers)
- LangGraph StateGraph construction
- ReAct-style agent loop

No external dependencies beyond AWS Bedrock.

### neo4j_simple_mcp_agent.ipynb

Full Neo4j integration using LangGraph and langchain-mcp-adapters. Demonstrates:
- Low-level MCP client with `streamablehttp_client`
- Proper AgentCore Gateway session handling (`terminate_on_close=False`)
- Loading MCP tools into LangGraph agent
- Querying Neo4j database schema and running Cypher queries

### neo4j_strands_mcp_agent.ipynb

Neo4j integration using AWS Strands Agents framework. Demonstrates:
- Strands Agent and BedrockModel setup
- MCPClient with transport factory pattern
- Token-based authentication with AgentCore Gateway
- Based on [official AWS AgentCore sample](https://github.com/awslabs/amazon-bedrock-agentcore-samples)

## Key Patterns

### Inference Profile with langchain-aws

```python
from langchain_aws import ChatBedrockConverse

llm = ChatBedrockConverse(
    model=INFERENCE_PROFILE_ARN,
    provider="anthropic",
    region_name=REGION,
    temperature=0,
    base_model_id=BASE_MODEL_ID,  # Bypasses bedrock:GetInferenceProfile permission
)
```

### MCP Gateway Connection

```python
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async with streamablehttp_client(
    GATEWAY_URL,
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    timeout=timedelta(seconds=120),
    terminate_on_close=False  # Required for AgentCore Gateway
) as (read_stream, write_stream, _):
    async with ClientSession(read_stream, write_stream) as session:
        await session.initialize()
        tools = await load_mcp_tools(session)
        # Use tools with your agent
```

## Resources

- [AWS Bedrock AgentCore Samples](https://github.com/awslabs/amazon-bedrock-agentcore-samples)
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [AWS Strands Agents](https://github.com/strands-agents/strands-agents)
- [MCP Server Deployment](../mcp-server/)
