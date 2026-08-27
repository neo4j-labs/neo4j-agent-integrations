"""Unit tests for MCP integration in CrewAI."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent.mcp import (
    DynamicMCPTool,
    _discover_oauth_metadata,
    _get_auth_headers,
    _get_oauth_token,
    is_mcp_enabled,
    load_mcp_tools,
)


def test_is_mcp_enabled(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    assert is_mcp_enabled() is False

    monkeypatch.setenv("MCP_SERVER_URL", "https://example.com/mcp")
    assert is_mcp_enabled() is True


def test_get_auth_headers_bearer(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret_token_123")
    monkeypatch.delenv("MCP_OAUTH_CLIENT_ID", raising=False)
    headers = _get_auth_headers("https://example.com/mcp")
    assert headers.get("Authorization") == "Bearer secret_token_123"


def test_get_auth_headers_basic(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("MCP_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password123")
    headers = _get_auth_headers("https://example.com/mcp")
    assert "Authorization" in headers
    assert headers["Authorization"].startswith("Basic ")


def test_get_oauth_token_client_credentials(monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_CLIENT_ID", "client_123")
    monkeypatch.setenv("MCP_OAUTH_CLIENT_SECRET", "secret_456")
    monkeypatch.setenv("MCP_OAUTH_TOKEN_URL", "https://api.neo4j.io/oauth/token")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "mock_jwt_access_token",
        "expires_in": 3600,
    }

    mock_httpx = MagicMock()
    mock_httpx.post.return_value = mock_resp
    mock_client_context = MagicMock()
    mock_client_context.__enter__.return_value = mock_httpx
    mock_client_context.__exit__.return_value = None

    with patch("httpx.Client", return_value=mock_client_context):
        token = _get_oauth_token("https://example.com/mcp")
        assert token == "mock_jwt_access_token"


def test_load_mcp_tools(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "https://example.com/mcp")
    monkeypatch.setattr("agent.mcp._HAS_MCP", True)

    mock_tools_meta = [
        {"name": "fetch_aura_metrics", "description": "Fetch database metrics", "input_schema": {}},
        {"name": "execute_cypher_remote", "description": "Run cypher on remote aura", "input_schema": {}},
    ]

    monkeypatch.setattr("agent.mcp._async_list_mcp_tools", AsyncMock(return_value=mock_tools_meta))

    tools = load_mcp_tools("https://example.com/mcp")
    assert len(tools) == 2
    names = [t.name for t in tools]
    assert "mcp_fetch_aura_metrics" in names
    assert "mcp_execute_cypher_remote" in names


def test_dynamic_mcp_tool_execution(monkeypatch):
    tool = DynamicMCPTool(
        name="mcp_test_tool",
        description="Test tool",
        server_url="https://example.com/mcp",
        target_tool_name="test_tool",
    )

    monkeypatch.setattr(
        "agent.mcp._async_call_mcp_tool",
        AsyncMock(return_value="Remote tool execution success result"),
    )

    result = tool._run(arguments=json.dumps({"param": "value"}))
    assert "success" in result
