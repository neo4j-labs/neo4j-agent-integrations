#!/usr/bin/env python3
"""
Neo4j MCP Agent with OAuth2 Token Refresh

A ReAct agent that connects to the Neo4j MCP server via AgentCore Gateway
and answers natural language questions about the database.

Features:
- Automatic OAuth2 token refresh before expiry
- LangChain ReAct agent pattern with AWS Bedrock Claude
- Demo mode with pre-configured queries

Usage:
    python oauth2_mcp_agent.py                    # Run demo queries
    python oauth2_mcp_agent.py "your question"    # Ask a specific question

Prerequisites:
    - Credentials file at ../mcp-server/.mcp-credentials.json
    - AWS credentials configured for Bedrock access
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient


# Credentials file location (from mcp-server deployment)
CREDENTIALS_FILE = Path(__file__).parent.parent / "mcp-server" / ".mcp-credentials.json"
MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"

SYSTEM_PROMPT = """You are a helpful Neo4j database assistant with access to tools that let you query a Neo4j graph database.

Your capabilities include:
- Retrieve the database schema to understand node labels, relationship types, and properties
- Execute read-only Cypher queries to answer questions about the data
- Do not execute any write Cypher queries

When answering questions about the database:
1. First retrieve the schema to understand the database structure
2. Formulate appropriate Cypher queries based on the actual schema
3. If a query returns no results, explain what you looked for and suggest alternatives
4. Format results in a clear, human-readable way
5. Cite the actual data returned in your response

Important Cypher notes:
- Use MATCH patterns that align with the actual schema
- For counting, use MATCH (n:Label) RETURN count(n)
- For listing items, add LIMIT to avoid overwhelming results
- Handle potential NULL values gracefully

Be concise but thorough in your responses."""


def load_credentials() -> dict:
    """Load credentials from ../mcp-server/.mcp-credentials.json."""
    if not CREDENTIALS_FILE.exists():
        print(f"ERROR: Credentials file not found: {CREDENTIALS_FILE}")
        print()
        print("Deploy the MCP server first:")
        print("  cd ../mcp-server && ./deploy.sh && ./deploy.sh credentials")
        sys.exit(1)

    with open(CREDENTIALS_FILE) as f:
        return json.load(f)


def check_token_expiry(credentials: dict) -> bool:
    """Check if the token is expired or expiring soon. Returns True if valid."""
    expires_at_str = credentials.get("token_expires_at")
    if not expires_at_str:
        return False

    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        now = datetime.now(timezone.utc)
        # Add 5 minute buffer to refresh before actual expiry
        return now < (expires_at - timedelta(minutes=5))
    except (ValueError, TypeError):
        return False


def refresh_token(credentials: dict) -> dict:
    """
    Refresh the OAuth2 access token using client credentials.

    Returns updated credentials dict with new token and expiry.
    """
    token_url = credentials.get("token_url")
    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    scope = credentials.get("scope")

    if not all([token_url, client_id, client_secret]):
        print("ERROR: Missing token refresh credentials (token_url, client_id, client_secret)")
        print("       Cannot auto-refresh token.")
        sys.exit(1)

    print("Refreshing OAuth2 token...")

    try:
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

        # Calculate expiry time
        expires_in = token_data.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Update credentials
        credentials["access_token"] = token_data["access_token"]
        credentials["token_expires_at"] = expires_at.isoformat()

        # Save updated credentials
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump(credentials, f, indent=2)

        print(f"Token refreshed. New expiry: {expires_at.isoformat()}")
        return credentials

    except httpx.HTTPStatusError as e:
        print(f"ERROR: Token refresh failed: {e.response.status_code}")
        print(f"       {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Token refresh failed: {e}")
        sys.exit(1)


def get_llm(region: str = "us-west-2"):
    """Get the LLM to use for the agent (AWS Bedrock Claude via Converse API)."""
    return init_chat_model(
        MODEL_ID,
        model_provider="bedrock_converse",
        region_name=region,
        temperature=0,
    )


async def run_agent(question: str):
    """Run the LangGraph agent with the given question."""
    print("=" * 70)
    print("Neo4j MCP Agent")
    print("=" * 70)
    print()

    # Load and validate credentials
    print("Loading credentials...")
    credentials = load_credentials()

    # Auto-refresh token if expired or expiring soon
    if not check_token_expiry(credentials):
        credentials = refresh_token(credentials)
        print()

    gateway_url = credentials["gateway_url"]
    access_token = credentials["access_token"]

    print(f"Gateway: {gateway_url}")
    print(f"Token expires: {credentials.get('token_expires_at')}")
    print()

    # Initialize LLM
    region = credentials.get("region", "us-west-2")
    print(f"Initializing LLM (Bedrock, region: {region})...")
    llm = get_llm(region)
    print(f"Using: {MODEL_ID}")
    print()

    # Connect to MCP server
    print("Connecting to MCP server...")

    client = MultiServerMCPClient(
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
    tools = await client.get_tools()
    print(f"Loaded {len(tools)} tools:")
    for tool in tools:
        print(f"  - {tool.name}")
    print()

    # Create the ReAct agent
    print("Creating agent...")
    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

    # Run the agent
    print("=" * 70)
    print(f"Question: {question}")
    print("=" * 70)
    print()

    result = await agent.ainvoke({"messages": [("human", question)]})

    # Extract and print the final response
    messages = result.get("messages", [])
    if messages:
        final_message = messages[-1]
        if hasattr(final_message, "content"):
            print("Answer:")
            print("-" * 70)
            print(final_message.content)
            print("-" * 70)
        else:
            print("Answer:", final_message)
    else:
        print("No response from agent")


# Demo questions showcasing the Aircraft Maintenance database
DEMO_QUESTIONS = [
    ("Database Schema Overview", "What is the database schema? Give me a brief summary."),
    ("Count of Aircraft", "How many Aircraft are in the database?"),
    ("List Airports", "List 5 airports with their city and country."),
    ("Recent Maintenance Events", "Show me 3 recent maintenance events with their severity."),
    ("Flight Statistics", "How many flights are in the database and what operators fly them?"),
]


async def run_demo():
    """Run demo queries to showcase the agent capabilities."""
    print()
    print("#" * 76)
    print("#" + " " * 74 + "#")
    print("#" + "NEO4J MCP AGENT DEMO".center(74) + "#")
    print("#" + " " * 74 + "#")
    print("#" * 76)
    print()

    for i, (title, question) in enumerate(DEMO_QUESTIONS, 1):
        print()
        print("=" * 76)
        print(f"  QUERY {i}: {title}")
        print("=" * 76)
        print()
        await run_agent(question)
        print()

    print()
    print("#" * 76)
    print("#" + "DEMO COMPLETE".center(74) + "#")
    print("#" * 76)
    print()
    print("Try your own questions:")
    print('  python oauth2_mcp_agent.py "Show aircraft with maintenance events"')
    print('  python oauth2_mcp_agent.py "What sensors monitor the engines?"')
    print('  python oauth2_mcp_agent.py "Find components needing attention"')


def main():
    if len(sys.argv) < 2:
        # No arguments - run demo mode
        asyncio.run(run_demo())
    else:
        # User provided a question
        question = " ".join(sys.argv[1:])
        asyncio.run(run_agent(question))


if __name__ == "__main__":
    main()
