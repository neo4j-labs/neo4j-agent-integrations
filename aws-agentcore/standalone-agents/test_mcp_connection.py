#!/usr/bin/env python3
"""
MCP Connection Test

Diagnostic tool for testing MCP connectivity using FastMCP client.
Tests gateway connection, tool discovery, and basic operations.

Usage:
    python test_mcp_connection.py

Prerequisites:
    - Credentials file at ../mcp-server/.mcp-credentials.json
"""

import asyncio
import json
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport


def load_credentials() -> dict:
    """Load credentials from ../mcp-server/.mcp-credentials.json"""
    creds_file = Path(__file__).parent.parent / "mcp-server" / ".mcp-credentials.json"
    if not creds_file.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_file}\n"
            "Deploy the MCP server first:\n"
            "  cd ../mcp-server && ./deploy.sh && ./deploy.sh credentials"
        )
    with open(creds_file) as f:
        return json.load(f)


async def test_connection():
    """Test MCP connection using FastMCP client."""
    creds = load_credentials()
    gateway_url = creds["gateway_url"]
    access_token = creds["access_token"]

    print(f"Gateway: {gateway_url[:60]}...")
    print(f"Token: {access_token[:30]}...")
    print("-" * 50)

    # Create FastMCP transport and client
    transport = StreamableHttpTransport(
        url=gateway_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    client = Client(transport)

    async with client:
        # List tools
        print("Listing tools...")
        tools = await client.list_tools()
        print(f"Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}")

        # Build tool map (handle Gateway prefix)
        tool_map = {}
        for t in tools:
            base = t.name.split("___")[-1] if "___" in t.name else t.name
            tool_map[base] = t.name

        # Test get-schema
        print("\n" + "-" * 50)
        print("Calling get-schema...")
        schema_tool = tool_map.get("get-schema", "get-schema")
        result = await client.call_tool(schema_tool, {})
        print(f"Result type: {type(result).__name__}")
        if hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text[:500])
        else:
            print(result)

        # Test read-cypher
        print("\n" + "-" * 50)
        print("Calling read-cypher...")
        cypher_tool = tool_map.get("read-cypher", "read-cypher")
        query = "MATCH (n) RETURN labels(n) AS label, count(*) AS count"
        result = await client.call_tool(cypher_tool, {"query": query})
        if hasattr(result, "content"):
            for item in result.content:
                if hasattr(item, "text"):
                    print(item.text[:500])
        else:
            print(result)

    print("\n" + "=" * 50)
    print("All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_connection())
