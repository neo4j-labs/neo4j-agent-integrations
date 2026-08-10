"""Optional MCP (Model Context Protocol) client for the DataRobot agent.

When MCP_SERVER_URL is set, the agent fetches tools dynamically from the MCP
server and adds them alongside the built-in Neo4j tools.

Supported transports (auto-detected by URL prefix):
  - Streamable HTTP  (modern MCP servers, url starting with http:// or https://)
  - SSE legacy       (older MCP servers, tried as fallback for http/https)
  - stdio            (any other string treated as a shell command)

Authentication (in priority order):
  1. MCP_OAUTH_CLIENT_ID + MCP_OAUTH_CLIENT_SECRET → OAuth 2.0 client-credentials
     grant against MCP_OAUTH_TOKEN_URL, sent as "Authorization: Bearer <token>".
     This is the machine-to-machine auth model used by hosted Neo4j Aura
     endpoints (Aura Agents, the Aura Management API) — see
     https://neo4j.com/docs/aura/api/authentication/. The resulting access
     token is cached in-process and refreshed automatically shortly before
     it expires.
  2. MCP_AUTH_TOKEN → static "Authorization: Bearer <token>"
  3. NEO4J_USERNAME + NEO4J_PASSWORD → Basic auth (matches the
     neo4j-mcp-official server convention, and a hosted Aura *database*
     instance's own credentials when pointing MCP_SERVER_URL at the MCP
     endpoint shown on the Aura Console "Inspect" tab for that instance)
  4. No auth headers

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
import sys
import time
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

# httpx is also needed for the OAuth token fetch, independently of whether
# the Streamable HTTP MCP transport is available (a direct dependency —
# see requirements.txt — so this should normally succeed whenever mcp does).
try:
    import httpx as _oauth_httpx  # type: ignore[import]
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

# Neo4j Aura's standard OAuth 2.0 client-credentials token endpoint (used by
# the Aura Management API and Aura Terraform provider — see
# https://neo4j.com/docs/aura/api/authentication/). Aura Agents hosted MCP
# endpoints are expected to use the same identity platform, but if a
# specific Aura Agent's setup screen shows a different token URL, override
# it with MCP_OAUTH_TOKEN_URL.
_DEFAULT_AURA_OAUTH_TOKEN_URL = "https://api.neo4j.io/oauth/token"

# In-process cache for the OAuth access token: {"token": str, "expires_at": float}.
# Refreshed automatically once within _TOKEN_REFRESH_MARGIN_S of expiry.
_oauth_token_cache: dict[str, Any] | None = None
_TOKEN_REFRESH_MARGIN_S = 30


# httpx's default timeout (5s) is too short for MCP servers reached through
# corporate proxies or cold-starting cloud services. Tool calls that execute
# a Neo4j query server-side can also take a while if the DB is unreachable
# (e.g. neo4j-mcp-official retries for up to ~30s before giving up), so the
# default here needs headroom above that. Configurable via MCP_HTTP_TIMEOUT
# (seconds).
_HTTP_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "90"))


def is_enabled() -> bool:
    return _HAS_MCP and bool(os.environ.get("MCP_SERVER_URL"))


def _warn_if_configured_but_unavailable() -> None:
    """Warn once if MCP_SERVER_URL is set but the ``mcp`` package couldn't be
    imported, instead of silently returning [] with zero feedback.

    Without this, a user who sets MCP_SERVER_URL but is on Python <3.10 (the
    ``mcp`` package's minimum) or simply forgot to install requirements sees
    zero tools and zero errors/warnings — indistinguishable from MCP being
    intentionally disabled. This has caused real confusion during testing.
    """
    if _HAS_MCP or not os.environ.get("MCP_SERVER_URL"):
        return
    logger.warning(
        "MCP_SERVER_URL is set to '%s' but the 'mcp' package is not "
        "importable, so MCP is disabled and list_tools()/call_tool() will "
        "silently return no results. The 'mcp' package requires Python "
        ">=3.10 (current interpreter: %s). Run 'pip install -r "
        "requirements.txt' with a Python >=3.10 interpreter to enable MCP.",
        os.environ.get("MCP_SERVER_URL", ""),
        sys.version.split()[0],
    )


def _is_http(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def _oauth_client_credentials_configured() -> bool:
    return bool(
        os.environ.get("MCP_OAUTH_CLIENT_ID") and os.environ.get("MCP_OAUTH_CLIENT_SECRET")
    )


async def _fetch_oauth_token() -> str | None:
    """Fetch (or return a cached) OAuth 2.0 client-credentials access token.

    Sends client_id/client_secret as HTTP Basic auth to MCP_OAUTH_TOKEN_URL
    (RFC 6749 s2.3.1 -- the convention used by Neo4j Aura's OAuth endpoint and
    most identity providers), with grant_type=client_credentials and any
    configured scope/audience. Returns None (non-fatal) on any failure so the
    caller falls back to no auth header rather than crashing the agent.
    """
    global _oauth_token_cache

    if not _HAS_HTTPX:
        logger.warning(
            "MCP_OAUTH_CLIENT_ID/SECRET are set but 'httpx' is not importable, "
            "so the OAuth token cannot be fetched. Run 'pip install -r "
            "requirements.txt' to install it."
        )
        return None

    now = time.time()
    if _oauth_token_cache and now < _oauth_token_cache["expires_at"] - _TOKEN_REFRESH_MARGIN_S:
        return _oauth_token_cache["token"]

    client_id = os.environ["MCP_OAUTH_CLIENT_ID"]
    client_secret = os.environ["MCP_OAUTH_CLIENT_SECRET"]
    token_url = os.environ.get("MCP_OAUTH_TOKEN_URL", _DEFAULT_AURA_OAUTH_TOKEN_URL)

    data: dict[str, str] = {"grant_type": "client_credentials"}
    scope = os.environ.get("MCP_OAUTH_SCOPE")
    if scope:
        data["scope"] = scope
    audience = os.environ.get("MCP_OAUTH_AUDIENCE")
    if audience:
        data["audience"] = audience

    try:
        async with _oauth_httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.post(token_url, data=data, auth=(client_id, client_secret))
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning(
            "OAuth client-credentials token fetch failed against %s (%s). "
            "Falling back to no auth header for this MCP request.",
            token_url,
            exc,
        )
        return None

    access_token = payload.get("access_token")
    if not access_token:
        logger.warning(
            "OAuth token endpoint %s returned no 'access_token' field (keys: %s).",
            token_url,
            list(payload.keys()),
        )
        return None

    expires_in = payload.get("expires_in", 300)
    _oauth_token_cache = {"token": access_token, "expires_at": now + float(expires_in)}
    return access_token


async def _auth_headers() -> dict[str, str]:
    """Build auth headers from env vars.

    Priority:
    1. MCP_OAUTH_CLIENT_ID + MCP_OAUTH_CLIENT_SECRET -> Bearer <oauth token>
       (hosted Neo4j Aura Agents / Aura Management API auth model)
    2. MCP_AUTH_TOKEN  -> Bearer <token>
    3. NEO4J_USERNAME + NEO4J_PASSWORD -> Basic auth (neo4j-mcp-official
       convention, and a hosted Aura database's own instance credentials)
    4. No auth headers
    """
    if _oauth_client_credentials_configured():
        token = await _fetch_oauth_token()
        if token:
            return {"Authorization": f"Bearer {token}"}
        # Fall through: if OAuth is configured but the fetch failed, still
        # try any other configured auth rather than sending zero headers.

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
    headers = await _auth_headers()
    if _HAS_STREAMABLE:
        try:
            http_client = _httpx.AsyncClient(headers=headers, timeout=_HTTP_TIMEOUT)
            # Newer mcp releases (>=1.10) yield a 3-tuple (read, write,
            # get_session_id_callback); older ones yield only (read, write).
            # The trailing "*_" absorbs the extra item on either version.
            async with streamable_http_client(url, http_client=http_client) as (read, write, *_):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return [_parse_tool(t) for t in result.tools]
        except Exception as exc:
            logger.warning(
                "MCP StreamableHTTP transport failed (%s); falling back to SSE. "
                "If this persists, check that the 'mcp' package is >=1.24.0 "
                "(older versions use an incompatible streamable_http_client signature).",
                _unwrap_exception(exc),
            )

    async with sse_client(url, headers=headers, timeout=_HTTP_TIMEOUT) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [_parse_tool(t) for t in result.tools]


async def _call_tool_http(url: str, name: str, arguments: dict[str, Any]) -> Any:
    """Try streamable HTTP first, fall back to SSE."""
    headers = await _auth_headers()
    if _HAS_STREAMABLE:
        try:
            http_client = _httpx.AsyncClient(headers=headers, timeout=_HTTP_TIMEOUT)
            async with streamable_http_client(url, http_client=http_client) as (read, write, *_):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments)
                    return _parse_content(result.content)
        except Exception as exc:
            logger.warning(
                "MCP StreamableHTTP transport failed for call_tool (%s); falling back to SSE. "
                "If this persists, check that the 'mcp' package is >=1.24.0 "
                "(older versions use an incompatible streamable_http_client signature).",
                _unwrap_exception(exc),
            )

    async with sse_client(url, headers=headers, timeout=_HTTP_TIMEOUT) as (read, write):
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
        _warn_if_configured_but_unavailable()
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
        _warn_if_configured_but_unavailable()
        return {"error": "MCP not configured"}
    url = os.environ["MCP_SERVER_URL"]
    try:
        return anyio.run(_call_tool_async, url, name, arguments)
    except Exception as exc:
        real_error = _unwrap_exception(exc)
        logger.warning("MCP call_tool '%s' failed: %s", name, real_error)
        return {"error": real_error}
