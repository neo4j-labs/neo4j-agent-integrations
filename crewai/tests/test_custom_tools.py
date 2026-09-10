"""Tests for reusable custom-tool CrewAI adapters."""
from __future__ import annotations

from unittest.mock import AsyncMock

import custom_tools

from agent.custom_tools import CustomNeo4jTool, get_custom_tools


def test_get_custom_tools_returns_all_wrappers_when_enabled(monkeypatch):
    monkeypatch.setenv("CUSTOM_TOOLS_ENABLED", "true")

    tools = get_custom_tools()

    assert len(tools) == 12
    assert "custom_search_news" in [tool.name for tool in tools]
    assert "custom_get_investments" in [tool.name for tool in tools]


def test_custom_tool_forwards_json_arguments(monkeypatch):
    search_companies = AsyncMock(return_value='[{"name": "Neo4j"}]')
    monkeypatch.setattr(custom_tools, "search_companies", search_companies)
    tool = CustomNeo4jTool(
        name="custom_search_companies",
        description="Search companies",
        target_tool_name="search_companies",
    )

    result = tool._run('{"search": "Neo4j"}')

    assert result == '[{"name": "Neo4j"}]'
    search_companies.assert_awaited_once_with(search="Neo4j")


def test_custom_tools_do_not_initialize_vertex_client_on_import():
    import custom_tools.custom_tools as module

    assert module._vertex_client is None
