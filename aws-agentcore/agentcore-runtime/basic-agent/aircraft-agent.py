#!/usr/bin/env python3
"""
Neo4j MCP Agent - AgentCore Runtime

A ReAct agent that connects to the Neo4j MCP server via AgentCore Gateway
and answers natural language questions about the database.

Deployed on Amazon Bedrock AgentCore Runtime.

Local testing:
    python aircraft-agent.py            # Start server on port 8080
    curl -X POST http://localhost:8080/invocations \
        -H "Content-Type: application/json" \
        -d '{"prompt": "What is the database schema?"}'

Cloud deployment:
    agentcore configure -e aircraft-agent.py
    agentcore deploy
    agentcore invoke '{"prompt": "What is the database schema?"}'
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Reduce noise from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Create the AgentCore app
app = BedrockAgentCoreApp()

# Configuration
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")

# In-memory caches (loaded once at startup, never written to disk)
_CREDENTIALS: dict | None = None
_CACHED_SCHEMA: str | None = None

SYSTEM_PROMPT_TEMPLATE = """You are a helpful Neo4j database assistant with access to tools that let you query a Neo4j graph database.

## Database Schema (Pre-loaded)

The database schema is already known - DO NOT call get-schema, use this instead:

{schema}

## Your Capabilities

- Execute read-only Cypher queries to answer questions about the data
- Do not execute any write Cypher queries

## Query Guidelines

When answering questions:
1. Use the schema above to formulate Cypher queries - no need to retrieve it
2. If a query returns no results, explain what you looked for and suggest alternatives
3. Format results in a clear, human-readable way
4. Cite the actual data returned in your response

## CRITICAL: Always Use LIMIT

**ALWAYS add LIMIT to every query that returns rows (not aggregations):**
- For listing/browsing queries: use `LIMIT 10` (or `LIMIT 25` max)
- For sample data: use `LIMIT 5`
- For aggregations (COUNT, SUM, AVG): LIMIT is optional
- NEVER return unlimited result sets

Examples:
- MATCH (a:Aircraft) RETURN a LIMIT 10  ✓
- MATCH (a:Aircraft) RETURN a  ✗ (missing LIMIT)
- MATCH (a:Aircraft) RETURN count(a)  ✓ (aggregation, LIMIT optional)

## Other Cypher Notes

- Use MATCH patterns that align with the actual schema
- For counting, use MATCH (n:Label) RETURN count(n)
- Handle potential NULL values gracefully

Be concise but thorough in your responses."""


def load_credentials() -> dict:
    """Load credentials from in-memory cache (loaded once at startup)."""
    global _CREDENTIALS

    if _CREDENTIALS is None:
        # Load from file once at startup
        credentials_file = Path(__file__).parent / ".mcp-credentials.json"
        if not credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {credentials_file}\n"
                "Create .mcp-credentials.json with gateway_url, access_token, etc."
            )
        with open(credentials_file) as f:
            _CREDENTIALS = json.load(f)
        logger.info("Credentials loaded into memory")

    return _CREDENTIALS


def check_token_expiry(credentials: dict) -> bool:
    """Check if the token is expired or expiring soon. Returns True if valid."""
    expires_at_str = credentials.get("token_expires_at")
    if not expires_at_str:
        return False

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        now = datetime.now(timezone.utc)
        return now < (expires_at - timedelta(minutes=5))
    except (ValueError, TypeError):
        return False


def refresh_token(credentials: dict) -> dict:
    """Refresh the OAuth2 access token using client credentials (in-memory only)."""
    token_url = credentials.get("token_url")
    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    scope = credentials.get("scope")

    if not all([token_url, client_id, client_secret]):
        raise ValueError(
            "Missing token refresh credentials (token_url, client_id, client_secret)"
        )

    logger.info("Refreshing OAuth2 token...")
    response = httpx.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()

    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Update in-memory credentials only (no file writes for cloud compatibility)
    credentials["access_token"] = token_data["access_token"]
    credentials["token_expires_at"] = expires_at.isoformat()

    logger.info(f"Token refreshed (in-memory). Expires: {expires_at.isoformat()}")
    return credentials


def get_llm(region: str = AWS_REGION):
    """Get the LLM to use for the agent (AWS Bedrock Claude via Converse API)."""
    import boto3
    bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    return init_chat_model(
        client=bedrock_client,
        model=MODEL_ID,
        model_provider="bedrock_converse",
        temperature=0,
    )


async def fetch_schema(gateway_url: str, access_token: str) -> str:
    """Fetch schema from the MCP server."""
    from datetime import timedelta
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with streamablehttp_client(
        gateway_url, headers, timeout=timedelta(seconds=60), terminate_on_close=False
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # Get tool map to handle Gateway prefixing
            result = await session.list_tools()
            tool_map = {}
            for tool in result.tools:
                full_name = tool.name
                if "___" in full_name:
                    base_name = full_name.split("___", 1)[1]
                else:
                    base_name = full_name
                tool_map[base_name] = full_name

            # Call get-schema
            schema_tool = tool_map.get("get-schema")
            if not schema_tool:
                return "Schema not available"

            result = await session.call_tool(schema_tool, {})
            if result.content:
                return result.content[0].text
            return "Schema not available"


async def get_cached_schema(gateway_url: str, access_token: str) -> str:
    """Get schema from cache or fetch it."""
    global _CACHED_SCHEMA

    if _CACHED_SCHEMA is None:
        logger.info("Fetching schema from MCP server (first request)...")
        _CACHED_SCHEMA = await fetch_schema(gateway_url, access_token)
        logger.info(f"Schema cached ({len(_CACHED_SCHEMA)} bytes)")

    return _CACHED_SCHEMA


def extract_prompt_from_payload(payload: dict) -> tuple[str | None, str, str]:
    """
    Extract prompt and context from payload, supporting multiple field names.

    Args:
        payload: Request payload dictionary

    Returns:
        Tuple of (prompt, session_id, user_id)
    """
    # Support multiple field names for flexibility
    prompt = (
        payload.get("prompt")
        or payload.get("message")
        or payload.get("query")
        or payload.get("inputText")
        or payload.get("input")
    )

    session_id = payload.get("session_id", "default_session")
    user_id = payload.get("user_id", "default_user")

    return prompt, session_id, user_id


@app.entrypoint
async def invoke(payload: dict = None):
    """
    AgentCore Runtime handler function.

    Connects to Neo4j MCP server via Gateway and processes natural language queries.

    Args:
        payload: Event payload containing 'prompt', 'message', 'query', or 'inputText'

    Yields:
        dict: Response chunks for streaming
    """
    logger.info(f"Received request with payload keys: {list(payload.keys()) if payload else []}")

    if payload is None:
        payload = {}

    # Extract prompt from various possible fields
    prompt, session_id, user_id = extract_prompt_from_payload(payload)

    if not prompt:
        logger.warning("No prompt provided in request")
        yield {"type": "error", "error": "No prompt provided. Please include 'prompt' in your request."}
        return

    logger.info(f"Processing query for user {user_id}, session {session_id}: {prompt[:100]}...")

    try:
        # Load and validate credentials
        logger.info("Loading credentials...")
        credentials = load_credentials()

        # Auto-refresh token if expired
        if not check_token_expiry(credentials):
            credentials = refresh_token(credentials)

        gateway_url = credentials["gateway_url"]
        access_token = credentials["access_token"]
        region = credentials.get("region", AWS_REGION)

        logger.info(f"Gateway: {gateway_url}")
        logger.info(f"Model: {MODEL_ID}")

        # Get cached schema (fetched once on first request)
        schema = await get_cached_schema(gateway_url, access_token)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=schema)

        # Initialize LLM
        llm = get_llm(region)

        # Connect to MCP server via Gateway using context manager
        logger.info("Connecting to MCP server...")
        mcp_client = MultiServerMCPClient(
            {
                "neo4j": {
                    "transport": "streamable_http",
                    "url": gateway_url,
                    "headers": {
                        "Authorization": f"Bearer {access_token}",
                    },
                }
            }
        )

        # Get available tools
        tools = await mcp_client.get_tools()
        logger.info(f"Loaded {len(tools)} tools: {[t.name for t in tools]}")

        # Create the ReAct agent (LangGraph best practice pattern)
        agent = create_agent(llm, tools, system_prompt=system_prompt)

        # Run the agent with streaming
        logger.info("Running agent...")
        response_text = ""
        async for message_chunk, metadata in agent.astream(
            {"messages": [("human", prompt)]},
            stream_mode="messages"
        ):
            if message_chunk.content:
                for content in message_chunk.content:
                    if isinstance(content, dict) and 'text' in content:
                        response_text += content['text']
                    elif isinstance(content, str):
                        response_text += content

        if not response_text:
            response_text = "No response from agent"

        # Stream the response in chunks (for compatibility with streaming clients)
        yield {"type": "chunk", "data": response_text}
        yield {"type": "complete"}

        logger.info("Request completed successfully")

    except FileNotFoundError as e:
        logger.error(f"Credentials error: {e}")
        yield {
            "type": "error",
            "error": str(e),
        }
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        yield {
            "type": "error",
            "error": f"HTTP error {e.response.status_code}: {e.response.text}",
        }
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        yield {
            "type": "error",
            "error": f"Error processing your request: {str(e)}\n\nPlease try rephrasing your question or check the logs.",
        }


if __name__ == "__main__":
    logger.info(f"Starting Neo4j MCP Agent with model: {MODEL_ID}")
    app.run()
