# Standalone Agent Samples

Local Python scripts for testing and demonstrating Neo4j MCP integration without AgentCore Runtime deployment.

## Samples

| Script | Description | Key Pattern |
|--------|-------------|-------------|
| [oauth2_mcp_agent.py](./oauth2_mcp_agent.py) | ReAct agent with OAuth2 token refresh | Auto token refresh, LangChain agent |
| [test_mcp_connection.py](./test_mcp_connection.py) | MCP connectivity diagnostic tool | FastMCP client, tool discovery |

## Prerequisites

1. **Python 3.10+** with dependencies installed
2. **AWS credentials** configured for Bedrock access
3. **Deployed MCP Server** with credentials file at `../mcp-server/.mcp-credentials.json`

See [../mcp-server/](../mcp-server/) for deployment instructions.

## Setup

Install dependencies:

```bash
pip install langchain langchain-mcp-adapters httpx fastmcp
```

Or with uv:

```bash
uv pip install langchain langchain-mcp-adapters httpx fastmcp
```

## Usage

### oauth2_mcp_agent.py

A production-ready ReAct agent that:
- Automatically refreshes OAuth2 tokens before expiry
- Connects to Neo4j via AgentCore Gateway MCP
- Uses AWS Bedrock Claude for reasoning

```bash
# Run demo queries
python oauth2_mcp_agent.py

# Ask a specific question
python oauth2_mcp_agent.py "What is the database schema?"
python oauth2_mcp_agent.py "How many nodes are in the database?"
```

**Key Features:**
- Token expiry checking with 5-minute buffer
- Client credentials flow for token refresh
- Credentials persistence to JSON file
- Demo mode with pre-configured queries

### test_mcp_connection.py

A lightweight diagnostic tool for testing MCP connectivity:

```bash
python test_mcp_connection.py
```

**What it tests:**
- Gateway connection with Bearer token auth
- Tool discovery (lists available MCP tools)
- Schema retrieval (`get-schema` tool)
- Cypher query execution (`read-cypher` tool)

**Key Features:**
- FastMCP client with StreamableHttpTransport
- Gateway prefix handling for tool names
- Minimal dependencies for quick diagnostics

## Key Patterns

### OAuth2 Token Refresh

```python
def check_token_expiry(credentials: dict) -> bool:
    """Check if token is expired or expiring soon."""
    expires_at = datetime.fromisoformat(credentials["token_expires_at"])
    now = datetime.now(timezone.utc)
    # 5 minute buffer
    return now < (expires_at - timedelta(minutes=5))

def refresh_token(credentials: dict) -> dict:
    """Refresh using client credentials flow."""
    response = httpx.post(
        credentials["token_url"],
        data={
            "grant_type": "client_credentials",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "scope": credentials["scope"],
        },
    )
    # Update and persist credentials...
```

### FastMCP Gateway Connection

```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

transport = StreamableHttpTransport(
    url=gateway_url,
    headers={"Authorization": f"Bearer {access_token}"},
)
client = Client(transport)

async with client:
    tools = await client.list_tools()
    result = await client.call_tool("get-schema", {})
```

## Comparison with Other Samples

| Location | Deployment | Use Case |
|----------|------------|----------|
| `standalone-agents/` (here) | Local execution | Development, testing, patterns |
| `agentcore-runtime/` | AgentCore Runtime | Production deployment |
| `sagemaker-samples/` | SageMaker Studio | Notebook-based exploration |

## Resources

- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [MCP Server Deployment](../mcp-server/)
