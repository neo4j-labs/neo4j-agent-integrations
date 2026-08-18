"""Tests for `agent/myagent.py`'s MCP tool loading helpers.

Covers the JSON-Schema -> Pydantic conversion and LangChain `StructuredTool`
wrapping used by `mcp_tools_context()` to expose external MCP tools (e.g.
the hosted Neo4j Aura MCP server) to the LangGraph agent — this repo's own
RFC-9728-OAuth-aware `mcp_client.py`, not `datarobot_genai`'s built-in MCP
adapter (see `mcp_tools_context`'s docstring for why).
"""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import BaseTool

from agent.myagent import (
    _build_mcp_langchain_tool,
    _mcp_tool_args_schema,
    mcp_tools_context,
)


class TestMcpToolArgsSchema:
    def test_returns_none_for_empty_schema(self):
        assert _mcp_tool_args_schema({}) is None
        assert _mcp_tool_args_schema({"properties": {}}) is None

    def test_builds_model_with_required_and_optional_fields(self):
        model = _mcp_tool_args_schema(
            {
                "properties": {
                    "search": {"type": "string", "description": "search text"},
                    "limit": {"type": "integer", "description": "max results"},
                },
                "required": ["search"],
            }
        )
        assert model is not None
        instance = model(search="Tesla")
        assert instance.search == "Tesla"
        assert instance.limit is None


class TestBuildMcpLangchainTool:
    def test_wraps_tool_def_as_structured_tool(self):
        tool_def = {
            "name": "search_companies",
            "description": "Search for companies",
            "inputSchema": {
                "properties": {"search": {"type": "string"}},
                "required": ["search"],
            },
        }
        tool = _build_mcp_langchain_tool(tool_def)
        assert isinstance(tool, BaseTool)
        assert tool.name == "search_companies"

    def test_falls_back_to_default_description(self):
        tool = _build_mcp_langchain_tool({"name": "no_description_tool"})
        assert "no_description_tool" in tool.description


class TestMcpToolsContext:
    @pytest.mark.asyncio
    async def test_yields_empty_list_when_mcp_disabled(self):
        with patch("agent.myagent.mcp_client.is_enabled", return_value=False):
            async with mcp_tools_context() as tools:
                assert tools == []

    @pytest.mark.asyncio
    async def test_yields_wrapped_tools_when_mcp_enabled(self):
        tool_defs = [{"name": "search_companies", "description": "search"}]
        with (
            patch("agent.myagent.mcp_client.is_enabled", return_value=True),
            patch(
                "agent.myagent.mcp_client.alist_tools",
                new=AsyncMock(return_value=tool_defs),
            ),
        ):
            async with mcp_tools_context() as tools:
                assert len(tools) == 1
                assert tools[0].name == "search_companies"

    @pytest.mark.asyncio
    async def test_yields_empty_list_on_error_not_raises(self):
        with (
            patch("agent.myagent.mcp_client.is_enabled", return_value=True),
            patch(
                "agent.myagent.mcp_client.alist_tools",
                new=AsyncMock(side_effect=RuntimeError("connection failed")),
            ),
        ):
            async with mcp_tools_context() as tools:
                assert tools == []
