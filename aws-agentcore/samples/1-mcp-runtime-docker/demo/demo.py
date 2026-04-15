"""
Standalone demo client for testing a deployed AWS AgentCore MCP Runtime
with the Neo4j MCP server.

Usage:
    cd demo
    uv sync
    uv run python demo.py [--mode list|call|agent|all]

Configuration is loaded from ../.env (the parent directory's .env file).
Required variables:
    AGENTCORE_RUNTIME_ARN  - ARN of the deployed runtime (auto-set by deploy.sh)
    NEO4J_USERNAME         - Neo4j database username
    NEO4J_PASSWORD         - Neo4j database password
Optional:
    AWS_REGION             - AWS region (defaults to boto3 session default)
"""

import argparse
import base64
import sys
from pathlib import Path
from urllib.parse import quote

import boto3
from dotenv import load_dotenv
import os


def load_config():
    """Load configuration from ../.env file."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        print(f"Error: .env file not found at {env_path}")
        print("Copy .env.sample to .env and fill in your values, then run ./deploy.sh")
        sys.exit(1)

    load_dotenv(env_path)

    arn = os.getenv("AGENTCORE_RUNTIME_ARN", "")
    if not arn:
        print("Error: AGENTCORE_RUNTIME_ARN is not set in .env")
        print("Run './deploy.sh deploy' to deploy the stack and auto-populate the ARN.")
        sys.exit(1)

    username = os.getenv("NEO4J_USERNAME", "")
    password = os.getenv("NEO4J_PASSWORD", "")
    if not username or not password:
        print("Error: NEO4J_USERNAME and NEO4J_PASSWORD must be set in .env")
        sys.exit(1)

    region = os.getenv("AWS_REGION") or boto3.Session().region_name

    return arn, username, password, region


def create_mcp_client(arn, username, password, region):
    """Create and return a configured MCPClient."""
    from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
    from strands.tools.mcp import MCPClient

    encoded_arn = quote(arn, safe="")
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    auth_header = f"Basic {credentials}"

    endpoint = (
        f"https://bedrock-agentcore.{region}.amazonaws.com"
        f"/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"
    )

    mcp_client = MCPClient(lambda: aws_iam_streamablehttp_client(
        endpoint=endpoint,
        aws_region=region,
        aws_service="bedrock-agentcore",
        headers={
            "X-Amzn-Bedrock-AgentCore-Runtime-Custom-Authorization": auth_header,
        },
    ))
    return mcp_client


def do_list_tools(mcp_client):
    """List all available MCP tools."""
    print("\n=== Listing MCP Tools ===\n")
    tools = mcp_client.list_tools_sync()
    for t in tools:
        name = t.tool_name
        desc = t.tool_spec.get("description", "(no description)")
        print(f"  - {name}: {desc}")
    print(f"\n  Total: {len(tools)} tools")
    return tools


def do_call_tool(mcp_client):
    """Call the get-schema tool directly."""
    print("\n=== Calling get-schema Tool ===\n")
    result = mcp_client.call_tool_sync("1", "get-schema")
    print(result)


def do_agent_query(mcp_client, query):
    """Run a natural language query via the Strands Agent."""
    from strands import Agent

    print("\n=== Running Agent Query ===\n")
    print(f"  Query: {query}\n")
    agent = Agent(tools=[mcp_client])
    response = agent(query)
    print(f"\n  Response: {response}")


def main():
    parser = argparse.ArgumentParser(
        description="Demo client for AWS AgentCore Neo4j MCP Runtime"
    )
    parser.add_argument(
        "--mode",
        choices=["list", "call", "agent", "all"],
        default="all",
        help="Demo mode: list tools, call a tool, run agent, or all (default: all)",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Natural language query for agent mode (prompted interactively if not provided)",
    )
    args = parser.parse_args()

    arn, username, password, region = load_config()
    print(f"Runtime ARN: {arn}")
    print(f"Neo4j User:  {username}")
    print(f"AWS Region:  {region}")

    mcp_client = create_mcp_client(arn, username, password, region)

    try:
        if args.mode in ("list", "call", "all"):
            mcp_client.start()

        if args.mode in ("list", "all"):
            do_list_tools(mcp_client)

        if args.mode in ("call", "all"):
            do_call_tool(mcp_client)

        if args.mode in ("call", "agent", "all"):
            if args.mode in ("call", "all"):
                mcp_client.stop(None, None, None)
            query = args.query or input("\nEnter your query: ")
            do_agent_query(mcp_client, query)

    finally:
        try:
            mcp_client.stop(None, None, None)
        except Exception:
            pass
        print("\nMCP client stopped.")


if __name__ == "__main__":
    main()
