"""
MCP (Model Context Protocol) Integration for CrewAI.

Provides native MCP client integration for CrewAI agents, allowing agents to
dynamically discover and call tools on external MCP servers.

Supports:
- HTTP / Streamable HTTP transports
- SSE (Server-Sent Events) transports
- Stdio subprocess transports
- Hosted Neo4j Aura MCP OAuth 2.0 authentication (Client Credentials Grant with RFC 9728 discovery)
- Static Bearer Token and Basic Auth
- Error resiliency: non-blocking, non-fatal fallback if MCP server is unreachable
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shlex
import time
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    import anyio
    _HAS_MCP = True
    try:
        from mcp.client.streamable_http import streamable_http_client
        _HAS_STREAMABLE = True
    except ImportError:
        _HAS_STREAMABLE = False
except ImportError:
    _HAS_MCP = False
    _HAS_STREAMABLE = False

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

_DEFAULT_AURA_OAUTH_TOKEN_URL = "https://api.neo4j.io/oauth/token"
_oauth_token_cache: dict[str, Any] | None = None
_TOKEN_REFRESH_MARGIN_S = 30
_oauth_discovery_cache: dict[str, dict[str, Any]] = {}
_HTTP_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "90"))


def is_mcp_enabled() -> bool:
    """Check if MCP is enabled via environment variables."""
    return bool(os.environ.get("MCP_SERVER_URL"))


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _discover_oauth_metadata(server_url: str) -> dict[str, Any]:
    """Discover OAuth 2.0 metadata via RFC 9728 protected resource metadata."""
    if server_url in _oauth_discovery_cache:
        return _oauth_discovery_cache[server_url]

    if not _HAS_HTTPX or not _is_http(server_url):
        return {}

    well_known_url = server_url.rstrip("/") + "/.well-known/oauth-protected-resource"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.get(well_known_url)
            if resp.status_code == 200:
                data = resp.json()
                auth_servers = data.get("authorization_servers", [])
                token_url = None
                if auth_servers and isinstance(auth_servers, list):
                    token_url = auth_servers[0].rstrip("/") + "/token"
                meta = {
                    "token_url": token_url or data.get("token_endpoint"),
                    "audience": data.get("resource"),
                }
                _oauth_discovery_cache[server_url] = meta
                return meta
    except Exception as e:
        logger.debug(f"OAuth discovery at {well_known_url} skipped: {e}")

    _oauth_discovery_cache[server_url] = {}
    return {}


def _get_oauth_token(server_url: str) -> str | None:
    """Obtain an OAuth 2.0 access token using client credentials grant."""
    client_id = os.environ.get("MCP_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("MCP_OAUTH_CLIENT_SECRET")
    if not (client_id and client_secret and _HAS_HTTPX):
        return None

    global _oauth_token_cache
    now = time.time()
    if _oauth_token_cache and _oauth_token_cache.get("expires_at", 0) > now + _TOKEN_REFRESH_MARGIN_S:
        return _oauth_token_cache["token"]

    discovered = _discover_oauth_metadata(server_url) if server_url else {}
    token_url = (
        os.environ.get("MCP_OAUTH_TOKEN_URL")
        or discovered.get("token_url")
        or _DEFAULT_AURA_OAUTH_TOKEN_URL
    )

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    audience = os.environ.get("MCP_OAUTH_AUDIENCE") or discovered.get("audience")
    if audience:
        data["audience"] = audience
    scope = os.environ.get("MCP_OAUTH_SCOPE")
    if scope:
        data["scope"] = scope

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            resp = client.post(token_url, data=data)
            resp.raise_for_status()
            payload = resp.json()
            access_token = payload.get("access_token")
            expires_in = int(payload.get("expires_in", 3600))
            if access_token:
                _oauth_token_cache = {
                    "token": access_token,
                    "expires_at": now + expires_in,
                }
                return access_token
    except Exception as exc:
        # Log only the exception class name to avoid leaking client secret or token data
        logger.warning(
            "Failed to fetch MCP OAuth token (%s). Falling back to unauthenticated request.",
            type(exc).__name__,
        )

    return None


def _get_auth_headers(server_url: str) -> dict[str, str]:
    """Resolve authentication headers for MCP requests."""
    token = _get_oauth_token(server_url)
    if token:
        return {"Authorization": f"Bearer {token}"}

    auth_token = os.environ.get("MCP_AUTH_TOKEN")
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}

    username = os.environ.get("NEO4J_USERNAME")
    password = os.environ.get("NEO4J_PASSWORD")
    if username and password:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}

    return {}


async def _async_list_mcp_tools(server_url: str) -> list[dict[str, Any]]:
    """Connect to MCP server and list available tools asynchronously."""
    if not _HAS_MCP:
        return []

    headers = _get_auth_headers(server_url)

    try:
        if _is_http(server_url):
            if _HAS_STREAMABLE:
                async with streamable_http_client(server_url, headers=headers) as (read_s, write_s, _):
                    async with ClientSession(read_s, write_s) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        return [
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "input_schema": tool.inputSchema,
                            }
                            for tool in tools_result.tools
                        ]
            else:
                async with sse_client(server_url, headers=headers) as (read_s, write_s):
                    async with ClientSession(read_s, write_s) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        return [
                            {
                                "name": tool.name,
                                "description": tool.description or "",
                                "input_schema": tool.inputSchema,
                            }
                            for tool in tools_result.tools
                        ]
        else:
            # Stdio command
            cmd_parts = shlex.split(server_url)
            params = StdioServerParameters(command=cmd_parts[0], args=cmd_parts[1:])
            async with stdio_client(params) as (read_s, write_s):
                async with ClientSession(read_s, write_s) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    return [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "input_schema": tool.inputSchema,
                        }
                        for tool in tools_result.tools
                    ]
    except Exception as e:
        logger.warning(f"Could not load tools from MCP server at {server_url}: {e}")
        return []


async def _async_call_mcp_tool(server_url: str, tool_name: str, arguments: dict[str, Any]) -> str:
    """Call a specific tool on the MCP server asynchronously."""
    if not _HAS_MCP:
        return json.dumps({"error": "mcp library not available"})

    headers = _get_auth_headers(server_url)

    try:
        if _is_http(server_url):
            if _HAS_STREAMABLE:
                async with streamable_http_client(server_url, headers=headers) as (read_s, write_s, _):
                    async with ClientSession(read_s, write_s) as session:
                        await session.initialize()
                        res = await session.call_tool(tool_name, arguments=arguments)
                        content = [c.text for c in res.content if hasattr(c, "text")]
                        return "\n".join(content) if content else json.dumps(res.model_dump())
            else:
                async with sse_client(server_url, headers=headers) as (read_s, write_s):
                    async with ClientSession(read_s, write_s) as session:
                        await session.initialize()
                        res = await session.call_tool(tool_name, arguments=arguments)
                        content = [c.text for c in res.content if hasattr(c, "text")]
                        return "\n".join(content) if content else json.dumps(res.model_dump())
        else:
            cmd_parts = shlex.split(server_url)
            params = StdioServerParameters(command=cmd_parts[0], args=cmd_parts[1:])
            async with stdio_client(params) as (read_s, write_s):
                async with ClientSession(read_s, write_s) as session:
                    await session.initialize()
                    res = await session.call_tool(tool_name, arguments=arguments)
                    content = [c.text for c in res.content if hasattr(c, "text")]
                    return "\n".join(content) if content else json.dumps(res.model_dump())
    except Exception as e:
        logger.error(f"Error calling MCP tool '{tool_name}': {e}")
        return json.dumps({"error": f"MCP tool execution failed: {e}"})


class DynamicMCPToolInput(BaseModel):
    """Dynamic input container for MCP tools."""
    arguments: str = Field(default="{}", description="JSON string containing arguments for the MCP tool.")


class DynamicMCPTool(BaseTool):
    """CrewAI BaseTool wrapper that dispatches execution to an external MCP server."""
    name: str = "mcp_tool"
    description: str = "Execute an external MCP tool."
    server_url: str = ""
    target_tool_name: str = ""

    def _run(self, **kwargs: Any) -> str:
        # Flatten arguments or parse JSON if string
        args = kwargs
        if "arguments" in kwargs and len(kwargs) == 1:
            try:
                args = json.loads(kwargs["arguments"])
            except Exception:
                args = kwargs

        def _sync_run():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    _async_call_mcp_tool(self.server_url, self.target_tool_name, args),
                    loop
                )
                return future.result(timeout=int(_HTTP_TIMEOUT))
            else:
                return asyncio.run(_async_call_mcp_tool(self.server_url, self.target_tool_name, args))

        return _sync_run()


def load_mcp_tools(server_url: str | None = None) -> list[BaseTool]:
    """Discover tools from configured MCP server and return them as CrewAI BaseTool instances."""
    url = server_url or os.environ.get("MCP_SERVER_URL")
    if not url or not _HAS_MCP:
        return []

    try:
        tools_meta = asyncio.run(_async_list_mcp_tools(url))
    except Exception as e:
        logger.warning(f"Failed to fetch tools from MCP server: {e}")
        return []

    crew_tools: list[BaseTool] = []
    for meta in tools_meta:
        tool_name = meta["name"]
        tool_desc = meta.get("description") or f"MCP tool: {tool_name}"

        # Create dynamically subclassed or instantiated tool
        mcp_tool = DynamicMCPTool(
            name=f"mcp_{tool_name}",
            description=f"[MCP] {tool_desc}",
            server_url=url,
            target_tool_name=tool_name,
        )
        crew_tools.append(mcp_tool)

    return crew_tools
