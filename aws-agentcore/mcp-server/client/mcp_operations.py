#!/usr/bin/env python3
"""
Shared MCP Operations for Neo4j MCP Server

This module provides common MCP operations used by both local and cloud clients.
It handles connection, tool listing, testing, and tool invocation.

GATEWAY TOOL NAME MAPPING
=========================

When MCP tools are accessed through AWS AgentCore Gateway, tool names are
automatically prefixed with the Gateway target name:

    Original:  get-schema
    Gateway:   neo4j-mcp-server-target___get-schema

This prefixing is INTENTIONAL and REQUIRED for Gateway operation. It enables:

1. Multi-Target Disambiguation - Gateway can aggregate multiple MCP servers
   without tool name collisions
2. Request Routing - Gateway uses the prefix to route requests to the correct target
3. Cedar Policy Authorization - The prefixed name is the action identifier in policies

The MCP specification requires EXACT string matching between tool discovery
(tools/list) and invocation (tools/call). This means we must use the full
prefixed name when calling tools through Gateway.

This module implements dynamic tool discovery following AWS best practices:
- Discover actual tool names via tools/list at runtime
- Build a mapping from base names to full (possibly prefixed) names
- Resolve base names to actual names when calling tools

This pattern is used in all official AWS AgentCore samples:
- foundation_samples/simple-oauth-gateway/client/demo.py (lines 174-176)
- shopping-concierge-agent/gateway_client.py (line 142)
- AWS-operations-agent/mcp-tool-handler.py (lines 8-10)

See: https://github.com/awslabs/amazon-bedrock-agentcore-samples
See: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-tool-naming.html
"""

import json
from datetime import timedelta

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


# =============================================================================
# Connection
# =============================================================================


async def connect_and_run(mcp_url: str, operation, *args, headers: dict = None):
    """
    Connect to an MCP server and run an operation.

    Args:
        mcp_url: The MCP server endpoint URL
        operation: Async function to run with the session
        *args: Additional arguments to pass to the operation
        headers: Optional HTTP headers (e.g., for JWT auth)
    """
    if headers is None:
        headers = {}

    async with streamablehttp_client(
        mcp_url, headers, timeout=timedelta(seconds=120), terminate_on_close=False
    ) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            await operation(session, *args)


# =============================================================================
# Tool Name Resolution (Gateway Prefixing)
# =============================================================================
#
# AgentCore Gateway prefixes tool names with the target name:
#   {target_name}___{tool_name}
#
# Example: "neo4j-mcp-server-target___get-schema"
#
# This is documented AWS behavior for multi-target routing and Cedar policies.
# The functions below implement dynamic tool discovery following AWS best practices.
# =============================================================================


async def get_tool_map(session: ClientSession) -> dict[str, str]:
    """
    Build a map from base tool names to actual tool names.

    This function implements the dynamic tool discovery pattern recommended by AWS
    for Gateway clients. It handles both direct Runtime access (unprefixed tools)
    and Gateway access (tools prefixed with target name).

    The MCP specification requires exact string matching between discovery and
    invocation, so we must use whatever names are returned by tools/list.

    AWS Sample References:
        - foundation_samples/simple-oauth-gateway/client/demo.py:174-176
        - shopping-concierge-agent/gateway_client.py:142
        - AWS-operations-agent/mcp-tool-handler.py:8-10

    Returns:
        Dict mapping base names (e.g., 'get-schema') to actual names
        (e.g., 'neo4j-mcp-server-target___get-schema' via Gateway,
         or just 'get-schema' via direct Runtime access)

    Example:
        >>> tool_map = await get_tool_map(session)
        >>> print(tool_map)
        {
            'get-schema': 'neo4j-mcp-server-target___get-schema',
            'read-cypher': 'neo4j-mcp-server-target___read-cypher'
        }
    """
    result = await session.list_tools()
    tool_map = {}

    for tool in result.tools:
        # Store the full name (as returned by Gateway or Runtime)
        full_name = tool.name

        # Extract base name (after ___ prefix if present)
        # This allows client code to use friendly names like "get-schema"
        # while we handle the Gateway prefix internally
        if "___" in full_name:
            base_name = full_name.split("___", 1)[1]
        else:
            base_name = full_name

        tool_map[base_name] = full_name

    return tool_map


def resolve_tool_name(tool_map: dict[str, str], base_name: str) -> str:
    """
    Resolve a base tool name to the actual tool name.

    This function looks up the full (possibly Gateway-prefixed) tool name
    for a given base name. It allows client code to use friendly names
    like "get-schema" while correctly calling the Gateway-prefixed version.

    Args:
        tool_map: Map from base names to actual names (from get_tool_map)
        base_name: The base tool name (e.g., 'get-schema')

    Returns:
        The actual tool name to use with session.call_tool()
        (e.g., 'neo4j-mcp-server-target___get-schema')

    Raises:
        KeyError: If the tool is not found in the map

    Example:
        >>> tool_map = await get_tool_map(session)
        >>> actual_name = resolve_tool_name(tool_map, "get-schema")
        >>> result = await session.call_tool(actual_name, {})
    """
    if base_name in tool_map:
        return tool_map[base_name]
    raise KeyError(f"Unknown tool: {base_name}")


# =============================================================================
# Operations
# =============================================================================
#
# All operations use dynamic tool discovery to handle Gateway prefixing.
# This allows the same code to work with both Gateway and direct Runtime access.
# =============================================================================


async def run_full_tests(session: ClientSession):
    """
    Run the full MCP client test suite.

    This function demonstrates the Gateway tool name mapping pattern:
    1. Discover available tools via tools/list
    2. Build a mapping from base names to full (Gateway-prefixed) names
    3. Use resolve_tool_name() to get the actual name for each tool call

    This pattern is required because Gateway prefixes tool names with the
    target name (e.g., "neo4j-mcp-server-target___get-schema").
    """
    print("OK    Session initialized")
    print()

    # ==========================================================================
    # STEP 1: Discover tools and build the name mapping
    # ==========================================================================
    # Gateway prefixes tool names with target name: {target}___{tool}
    # We build a map so client code can use friendly names like "get-schema"
    # while calling the actual Gateway-prefixed names.
    # ==========================================================================
    print("=" * 60)
    print("AVAILABLE TOOLS")
    print("=" * 60)
    print()
    tool_result = await session.list_tools()
    tool_map = {}

    for tool in tool_result.tools:
        full_name = tool.name
        # Extract base name for mapping (handles Gateway prefix)
        if "___" in full_name:
            base_name = full_name.split("___", 1)[1]
        else:
            base_name = full_name
        tool_map[base_name] = full_name

        desc = tool.description.split("\n")[0] if tool.description else ""
        print(f"  {tool.name}")
        if desc:
            print(f"    {desc[:70]}")
        print()

    # ==========================================================================
    # STEP 2: Test tools using resolved names
    # ==========================================================================
    # We use resolve_tool_name() to convert friendly names to actual names.
    # This is the pattern used in all AWS AgentCore samples.
    # ==========================================================================
    print("=" * 60)
    print("TOOL TESTS")
    print("=" * 60)
    print()

    # Test 1: get-schema
    # Note: We call resolve_tool_name("get-schema") which returns the full
    # Gateway-prefixed name like "neo4j-mcp-server-target___get-schema"
    print("1. Testing get-schema...")
    try:
        actual_name = resolve_tool_name(tool_map, "get-schema")
        result = await session.call_tool(actual_name, {})
        if result.content and result.content[0].text:
            text = result.content[0].text
            if len(text) > 100:
                print(f"   Result: {text[:100]}... (truncated)")
            else:
                print(f"   Result: {text}")
            print("   PASSED")
        else:
            print("   FAILED: No content returned")
    except Exception as e:
        print(f"   FAILED: {e}")
    print()

    # Test 2: read-cypher with simple query
    print("2. Testing read-cypher (RETURN 1 as test)...")
    try:
        actual_name = resolve_tool_name(tool_map, "read-cypher")
        result = await session.call_tool(actual_name, {"query": "RETURN 1 as test"})
        if result.content and result.content[0].text:
            print(f"   Result: {result.content[0].text}")
            print("   PASSED")
        else:
            print("   FAILED: No content returned")
    except Exception as e:
        print(f"   FAILED: {e}")
    print()

    # Test 3: read-cypher with labels query
    print("3. Testing read-cypher (CALL db.labels())...")
    try:
        actual_name = resolve_tool_name(tool_map, "read-cypher")
        result = await session.call_tool(
            actual_name, {"query": "CALL db.labels() YIELD label RETURN label LIMIT 5"}
        )
        if result.content and result.content[0].text:
            print(f"   Result: {result.content[0].text}")
            print("   PASSED")
        else:
            print("   FAILED: No content returned")
    except Exception as e:
        print(f"   FAILED: {e}")
    print()

    # Test 4: read-cypher with count query
    print("4. Testing read-cypher (count nodes)...")
    try:
        actual_name = resolve_tool_name(tool_map, "read-cypher")
        result = await session.call_tool(
            actual_name, {"query": "MATCH (n) RETURN count(n) as nodeCount"}
        )
        if result.content and result.content[0].text:
            print(f"   Result: {result.content[0].text}")
            print("   PASSED")
        else:
            print("   FAILED: No content returned")
    except Exception as e:
        print(f"   FAILED: {e}")
    print()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)


async def list_tools(session: ClientSession):
    """
    List available MCP tools.

    Displays the full tool names as returned by the server. When accessed via
    Gateway, these will include the target prefix (e.g., "neo4j-mcp-server-target___get-schema").
    """
    result = await session.list_tools()
    for tool in result.tools:
        print(f"{tool.name}")
        if tool.description:
            desc = tool.description.split("\n")[0].strip()
            print(f"  {desc}")
        print()


async def get_schema(session: ClientSession):
    """
    Get Neo4j database schema.

    Uses dynamic tool discovery to handle Gateway prefixing:
    1. get_tool_map() discovers the actual tool name via tools/list
    2. resolve_tool_name() maps "get-schema" to the full prefixed name
    3. session.call_tool() is called with the actual name
    """
    tool_map = await get_tool_map(session)
    actual_name = resolve_tool_name(tool_map, "get-schema")
    result = await session.call_tool(actual_name, {})
    if result.content:
        print(result.content[0].text)


async def run_query(session: ClientSession):
    """
    Run a test query (node counts by label).

    Uses dynamic tool discovery to handle Gateway prefixing:
    1. get_tool_map() discovers the actual tool name via tools/list
    2. resolve_tool_name() maps "read-cypher" to the full prefixed name
    3. session.call_tool() is called with the actual name
    """
    tool_map = await get_tool_map(session)
    actual_name = resolve_tool_name(tool_map, "read-cypher")
    result = await session.call_tool(
        actual_name,
        {"query": "MATCH (n) RETURN labels(n)[0] as label, count(*) as count ORDER BY count DESC LIMIT 10"},
    )
    if result.content:
        print(result.content[0].text)


async def call_tool(session: ClientSession, tool_name: str, args_json: str):
    """
    Call a specific MCP tool with JSON arguments.

    Note: This function expects the FULL tool name (including Gateway prefix
    if applicable). For user-friendly access, use get_tool_map() and
    resolve_tool_name() to convert base names to actual names.

    Args:
        session: The MCP client session
        tool_name: The full tool name (e.g., "neo4j-mcp-server-target___get-schema")
        args_json: JSON string of tool arguments
    """
    args = json.loads(args_json)
    result = await session.call_tool(tool_name, args)
    if result.content:
        print("Result:", result.content[0].text)
    else:
        print("Result: (no content)")
