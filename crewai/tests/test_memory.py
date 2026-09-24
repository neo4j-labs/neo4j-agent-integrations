"""Unit tests for NAMS memory integration in CrewAI."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent.memory import (
    GetPreferencesTool,
    SaveMemoryFactTool,
    SearchMemoryTool,
    build_crew_memory,
    get_memory_tools,
    is_memory_configured,
)


@pytest.fixture
def mock_memory_client(monkeypatch):
    mock_client = MagicMock()
    mock_entity = MagicMock()
    mock_entity.display_name = "Google"
    mock_entity.description = "Global tech giant leading in search and cloud computing."

    mock_client.long_term.search_entities = AsyncMock(return_value=[mock_entity])
    mock_client.long_term.add_fact = AsyncMock(return_value=None)

    mock_pref = MagicMock()
    mock_pref.preference = "Concise bulleted summary"
    mock_client.long_term.search_preferences = AsyncMock(return_value=[mock_pref])

    mock_msg = MagicMock()
    mock_msg.content = "Prior analysis of Google acquisition history."
    mock_client.short_term.search_messages = AsyncMock(return_value=[mock_msg])

    monkeypatch.setattr("agent.memory.get_memory_client", lambda: mock_client)
    return mock_client


def test_is_memory_configured(monkeypatch):
    monkeypatch.setenv("MEMORY_API_KEY", "test_key")
    monkeypatch.setattr("agent.memory._HAS_NAMS", True)
    assert is_memory_configured() is True

    monkeypatch.delenv("MEMORY_API_KEY", raising=False)
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com")
    assert is_memory_configured() is True


def test_search_memory_tool(mock_memory_client):
    tool = SearchMemoryTool()
    res = tool._run(query="Google AI strategy", limit=5)
    parsed = json.loads(res)
    assert "memories" in parsed
    assert len(parsed["memories"]) > 0
    assert "Google" in parsed["memories"][0]


def test_save_memory_fact_tool(mock_memory_client):
    tool = SaveMemoryFactTool()
    res = tool._run(
        subject="Google",
        predicate="invests_in",
        content="Anthropic AI partnership and model deployment.",
    )
    parsed = json.loads(res)
    assert parsed.get("status") == "success"
    assert mock_memory_client.long_term.add_fact.called


def test_get_preferences_tool(mock_memory_client):
    tool = GetPreferencesTool()
    res = tool._run(category="reporting")
    parsed = json.loads(res)
    assert "preferences" in parsed
    assert len(parsed["preferences"]) > 0


def test_get_memory_tools_when_enabled(monkeypatch):
    monkeypatch.setattr("agent.memory.is_memory_configured", lambda: True)
    tools = get_memory_tools()
    assert len(tools) == 3
    names = [t.name for t in tools]
    assert "search_memory" in names
    assert "save_memory_fact" in names
    assert "get_preferences" in names


def test_build_crew_memory_when_available(monkeypatch):
    mock_crew_memory_cls = MagicMock()
    monkeypatch.setattr("agent.memory.Neo4jCrewMemory", mock_crew_memory_cls)
    monkeypatch.setattr("agent.memory.get_memory_client", lambda: MagicMock())

    mem = build_crew_memory(crew_id="test_crew")
    assert mem is not None
    assert mock_crew_memory_cls.called
