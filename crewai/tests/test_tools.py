"""Unit tests for Neo4j Knowledge Graph tools in CrewAI."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from agent.tools import (
    CompanyProfileTool,
    CompanyRelationshipsTool,
    ListIndustriesTool,
    RunCypherQueryTool,
    SearchCompaniesTool,
    execute_cypher,
    get_neo4j_tools,
)


@pytest.fixture
def mock_neo4j_driver(monkeypatch):
    mock_driver = MagicMock()
    mock_record = MagicMock()
    mock_record.data.return_value = {
        "company_id": "google",
        "name": "Google",
        "summary": "Technology company specialized in search and AI",
    }
    mock_summary = MagicMock()
    mock_keys = ["company_id", "name", "summary"]

    mock_driver.execute_query.return_value = ([mock_record], mock_summary, mock_keys)

    monkeypatch.setattr("agent.tools.get_driver", lambda: mock_driver)
    return mock_driver


def test_get_neo4j_tools_list():
    tools = get_neo4j_tools()
    assert len(tools) == 5
    tool_names = [t.name for t in tools]
    assert "search_companies" in tool_names
    assert "query_company_profile" in tool_names
    assert "analyze_company_relationships" in tool_names
    assert "run_cypher_query" in tool_names
    assert "list_industry_categories" in tool_names


def test_search_companies_tool(mock_neo4j_driver):
    tool = SearchCompaniesTool()
    result = tool._run(search="Google", limit=5)
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
    assert parsed[0]["name"] == "Google"
    assert mock_neo4j_driver.execute_query.called


def test_company_profile_tool(mock_neo4j_driver):
    tool = CompanyProfileTool()
    result = tool._run(company_name="Google")
    parsed = json.loads(result)
    assert isinstance(parsed, dict)
    assert parsed.get("name") == "Google"


def test_company_relationships_tool(mock_neo4j_driver):
    tool = CompanyRelationshipsTool()
    result = tool._run(company_name="Google", max_depth=2)
    parsed = json.loads(result)
    assert isinstance(parsed, (list, dict))


def test_run_cypher_query_blocks_write_statements():
    tool = RunCypherQueryTool()
    res = tool._run("CREATE (n:Node) RETURN n")
    parsed = json.loads(res)
    assert "error" in parsed
    assert "forbidden" in parsed["error"]


def test_run_cypher_query_success(mock_neo4j_driver):
    tool = RunCypherQueryTool()
    res = tool._run("MATCH (n:Organization) RETURN count(n) AS total")
    parsed = json.loads(res)
    assert isinstance(parsed, list)


def test_list_industries_tool(mock_neo4j_driver):
    tool = ListIndustriesTool()
    res = tool._run(limit=10)
    parsed = json.loads(res)
    assert isinstance(parsed, list)
