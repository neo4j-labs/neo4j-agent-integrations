"""Optional MCP (Model Context Protocol) client for the DataRobot agent.

When MCP_SERVER_URL is set, the agent fetches tools dynamically from the MCP
server and adds them alongside the built-in Neo4j tools.

Supported transports (auto-detected by URL prefix):
  - Streamable HTTP  (modern MCP servers, url starting with http:// or https://)
  - SSE legacy       (older MCP servers, tried as fallback for http/https)
  - stdio            (any other string treated as a shell command)

Authentication:
  - If MCP_AUTH_TOKEN is set, passed as "Authorization: Bearer <token>"
  - Otherwise if NEO4J_USERNAME + NEO4J_PASSWORD are set, passed as Basic auth
    (matches the neo4j-mcp-official server convention)

Error handling:
  - anyio TaskGroup wraps connection errors in an ExceptionGroup; we unwrap
    it to log the real cause instead of the cryptic "unhandled errors in a
    TaskGroup (1 sub-exception)" message.
  - All failures are non-fatal: list_tools returns [], call_tool returns an
    error dict, so the agent continues with its built-in Neo4j tools.
"""
from __future__ import annotations

import base64
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
    try:
        from mcp.client.streamable_http import streamable_http_client  # type: ignore[import]
        import httpx as _httpx  # type: ignore[import]
        _HAS_STREAMABLE = True
    except ImportError:
        _HAS_STREAMABLE = False
except ImportError:
    _HAS_MCP = False
    _HAS_STREAMABLE = False


def is_enabled() -> bool:
    return _HAS_MCP and bool(os.environ.get("MCP_SERVER_URL"))


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _auth_headers() -> dict[str, str]:
    """Build auth headers from env vars.

    Priority:
    1. MCP_AUTH_TOKEN  → Bearer token
    2. NEO4J_USERNAME + NEO4J_PASSWORD → Basic auth (neo4j-mcp-official convention)
    3. No auth headers
    """
    token = os.environ.get("MCP_AUTH_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}"}
    user = os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    if user and password:
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    return {}


def _unwrap_exception(exc: BaseException) -> str:
    """Extract the real error from an anyio ExceptionGroup / BaseExceptionGroup."""
    if hasattr(exc, "exceptions") and exc.exceptions:  # type: ignore[union-attr]
        inner = exc.exceptions[0]  # type: ignore[union-attr]
        return f"{type(inner).__name__}: {inner}"
    return str(exc)


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


async def _list_tools_http(url: str) -> list[dict[str, Any]]:
    """Try streamable HTTP first, fall back to SSE."""
    headers = _auth_headers()
    if _HAS_STREAMABLE:
        try:
            http_client = _httpx.AsyncClient(headers=headers)
            async with streamable_http_client(url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [_parse_tool(t) for t in result.tools]
        except Exception as exc:
            logger.debug("StreamableHTTP failed, trying SSE: %s", _unwrap_exception(exc))

    async with sse_client(url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_parse_tool(t) for t in result.tools]


async def _call_tool_http(url: str, name: str, arguments: dict[str, Any]) -> Any:
    """Try streamable HTTP first, fall back to SSE."""
    headers = _auth_headers()
    if _HAS_STREAMABLE:
        try:
            http_client = _httpx.AsyncClient(headers=headers)
            async with streamable_http_client(url, http_client=http_client) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    return _parse_content(result.content)
        except Exception as exc:
            logger.debug("StreamableHTTP failed for call_tool, trying SSE: %s", _unwrap_exception(exc))

    async with sse_client(url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return _parse_content(result.content)


async def _list_tools_async(url: str) -> list[dict[str, Any]]:
    if _is_http(url):
        return await _list_tools_http(url)
    parts = shlex.split(url)
    params = StdioServerParameters(command=parts[0], args=parts[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_parse_tool(t) for t in result.tools]


async def _call_tool_async(url: str, name: str, arguments: dict[str, Any]) -> Any:
    if _is_http(url):
        return await _call_tool_http(url, name, arguments)
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
        return anyio.run(_list_tools_async, url)
    except Exception as exc:
        logger.warning("MCP list_tools failed (non-fatal): %s", _unwrap_exception(exc))
        return []


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    """Call a tool on the MCP server. Returns error dict on failure."""
    if not is_enabled():
        return {"error": "MCP not configured"}
    url = os.environ["MCP_SERVER_URL"]
    try:
        return anyio.run(_call_tool_async, url, name, arguments)
    except Exception as exc:
        real_error = _unwrap_exception(exc)
        logger.warning("MCP call_tool '%s' failed: %s", name, real_error)
        return {"error": real_error}
