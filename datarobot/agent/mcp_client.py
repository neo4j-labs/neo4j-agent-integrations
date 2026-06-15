"""Optional MCP (Model Context Protocol) client for the DataRobot agent.

When MCP_SERVER_URL is set, the agent fetches tools dynamically from the MCP
server and adds them alongside the built-in Neo4j tools.

Supported transports:
  - HTTP / SSE  (url starting with http:// or https://)
  - stdio       (any other string treated as a shell command)

The MCP library uses anyio internally — we run it with anyio.run() to avoid
the "unhandled errors in a TaskGroup" error that occurs with asyncio.run().
"""
from __future__ import annotations

import json
import logging
import os
import shlex
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession  # type: ignore[import]
    from mcp.client.sse import sse_client  # type: ignore[import]
    from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore[import]
    import anyio  # type: ignore[import]
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


def is_enabled() -> bool:
    return _HAS_MCP and bool(os.environ.get("MCP_SERVER_URL"))


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _parse_tool(t: Any) -> dict[str, Any]:
    return {
        "name": t.name,
        "description": t.description or "",
        "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
    }


def _parse_content(content: list[Any]) -> Any:
    if not content:
        return {}
    if len(content) == 1:
        return content[0].text if hasattr(content[0], "text") else str(content[0])
    return [c.text if hasattr(c, "text") else str(c) for c in content]


async def _list_tools_async(url: str) -> list[dict[str, Any]]:
    if _is_http(url):
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_parse_tool(t) for t in result.tools]
    else:
        parts = shlex.split(url)
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [_parse_tool(t) for t in result.tools]


async def _call_tool_async(url: str, name: str, arguments: dict[str, Any]) -> Any:
    if _is_http(url):
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return _parse_content(result.content)
    else:
        parts = shlex.split(url)
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return _parse_content(result.content)


def list_tools() -> list[dict[str, Any]]:
    """Fetch tool definitions from the MCP server. Returns [] on any error."""
    if not is_enabled():
        return []
    url = os.environ["MCP_SERVER_URL"]
    try:
        # Use anyio.run() — MCP library uses anyio TaskGroups internally
        return anyio.run(_list_tools_async, url)
    except Exception as exc:
        logger.warning("MCP list_tools failed (non-fatal): %s", exc)
        return []


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call a tool on the MCP server. Returns error string on failure."""
    if not is_enabled():
        return {"error": "MCP not configured"}
    url = os.environ["MCP_SERVER_URL"]
    try:
        return anyio.run(_call_tool_async, url, name, arguments)
    except Exception as exc:
        logger.warning("MCP call_tool '%s' failed: %s", name, exc)
        return {"error": str(exc)}
