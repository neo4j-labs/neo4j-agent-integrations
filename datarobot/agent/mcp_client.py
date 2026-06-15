"""Optional MCP (Model Context Protocol) client for the DataRobot agent.

When MCP_SERVER_URL is set, the agent fetches tools dynamically from the MCP
server and adds them alongside the built-in Neo4j tools.  If the `mcp` package
is not installed or the env var is absent, this module is a silent no-op.

Supported transports:
  - HTTP / SSE  (http:// or https://)
  - stdio       (any other string, treated as a shell command)
"""
from __future__ import annotations

import asyncio
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
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


def is_enabled() -> bool:
    return _HAS_MCP and bool(os.environ.get("MCP_SERVER_URL"))


def _server_url() -> str:
    return os.environ.get("MCP_SERVER_URL", "")


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


async def _list_tools_async(url: str) -> list[dict[str, Any]]:
    if _is_http(url):
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
                    }
                    for t in result.tools
                ]
    else:
        parts = shlex.split(url)
        params = StdioServerParameters(command=parts[0], args=parts[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
                    }
                    for t in result.tools
                ]


async def _call_tool_async(url: str, name: str, arguments: dict[str, Any]) -> Any:
    if _is_http(url):
        async with sse_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                parts = result.content
                if not parts:
                    return {}
                if len(parts) == 1:
                    return parts[0].text if hasattr(parts[0], "text") else str(parts[0])
                return [p.text if hasattr(p, "text") else str(p) for p in parts]
    else:
        parts_cmd = shlex.split(url)
        params = StdioServerParameters(command=parts_cmd[0], args=parts_cmd[1:])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                content = result.content
                if not content:
                    return {}
                if len(content) == 1:
                    return content[0].text if hasattr(content[0], "text") else str(content[0])
                return [c.text if hasattr(c, "text") else str(c) for c in content]


def list_tools() -> list[dict[str, Any]]:
    """Fetch tool definitions from the MCP server. Returns [] on any error."""
    if not is_enabled():
        return []
    url = _server_url()
    try:
        return asyncio.run(_list_tools_async(url))
    except Exception as exc:
        logger.warning("MCP list_tools failed (non-fatal): %s", exc)
        return []


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call a tool on the MCP server. Returns error dict on failure."""
    url = _server_url()
    try:
        return asyncio.run(_call_tool_async(url, name, arguments))
    except Exception as exc:
        logger.warning("MCP call_tool '%s' failed: %s", name, exc)
        return {"error": str(exc)}
