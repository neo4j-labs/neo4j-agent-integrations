"""Unit tests for the local MCP integration in CrewAI."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

from agent.mcp import (
    DynamicMCPTool,
    _local_mcp_environment,
    _server_parameters,
    get_local_mcp_command,
    is_mcp_enabled,
    load_mcp_tools,
)


def test_is_mcp_enabled(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_COMMAND", raising=False)
    assert is_mcp_enabled() is False

    monkeypatch.setenv("MCP_SERVER_COMMAND", "neo4j-mcp-server")
    assert is_mcp_enabled() is True


def test_local_mcp_command_is_trimmed(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_COMMAND", "  neo4j-mcp-server  ")

    assert get_local_mcp_command() == "neo4j-mcp-server"


def test_local_mcp_environment_uses_integration_database_settings(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://example.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password123")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    monkeypatch.delenv("NEO4J_MCP_URI", raising=False)

    environment = _local_mcp_environment()

    assert environment["NEO4J_MCP_URI"] == "neo4j+s://example.databases.neo4j.io"
    assert environment["NEO4J_MCP_USERNAME"] == "neo4j"
    assert environment["NEO4J_MCP_PASSWORD"] == "password123"
    assert environment["NEO4J_MCP_DATABASE"] == "neo4j"
    assert environment["NEO4J_MCP_READ_ONLY"] == "true"
    assert environment["NEO4J_TELEMETRY"] == "false"


def test_server_parameters_uses_local_command(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_COMMAND", "neo4j-mcp-server --debug")

    parameters = _server_parameters(get_local_mcp_command() or "")

    assert Path(parameters.command).name == "neo4j-mcp-server"
    assert parameters.args == ["--debug"]


def test_load_mcp_tools(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_COMMAND", "neo4j-mcp-server")
    monkeypatch.setattr("agent.mcp._HAS_MCP", True)

    mock_tools_metadata = [
        {"name": "get_schema", "description": "Get database schema", "input_schema": {}},
        {"name": "read_cypher", "description": "Run a read query", "input_schema": {}},
    ]
    monkeypatch.setattr(
        "agent.mcp._async_list_mcp_tools", AsyncMock(return_value=mock_tools_metadata)
    )

    tools = load_mcp_tools("neo4j-mcp-server")

    assert [tool.name for tool in tools] == ["mcp_get_schema", "mcp_read_cypher"]


def test_dynamic_mcp_tool_execution(monkeypatch):
    tool = DynamicMCPTool(
        name="mcp_test_tool",
        description="Test tool",
        server_command="neo4j-mcp-server",
        target_tool_name="test_tool",
    )
    monkeypatch.setattr(
        "agent.mcp._async_call_mcp_tool",
        AsyncMock(return_value="Local tool execution success result"),
    )

    result = tool._run(arguments=json.dumps({"param": "value"}))

    assert "success" in result
