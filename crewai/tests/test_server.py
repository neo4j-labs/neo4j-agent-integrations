"""Tests for the REST API."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import server


def test_chat_interface_is_served():
    response = TestClient(server.app).get("/")

    assert response.status_code == 200
    assert "Neo4j Graph Intelligence Assistant" in response.text
    assert 'action="/api/v1/query"' not in response.text
    assert 'fetch("/api/v1/query"' in response.text


def test_query_endpoint_runs_natural_language_query(monkeypatch):
    crew = MagicMock()
    crew.kickoff.return_value = "Verified graph answer"
    build_query_crew = MagicMock(return_value=crew)
    monkeypatch.setattr(server, "build_query_crew", build_query_crew)

    response = TestClient(server.app).post(
        "/api/v1/query",
        json={"query": "Which companies are connected to Google?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "query": "Which companies are connected to Google?",
        "status": "completed",
        "result": "Verified graph answer",
    }
    build_query_crew.assert_called_once_with(query="Which companies are connected to Google?")


def test_query_endpoint_rejects_empty_query():
    response = TestClient(server.app).post("/api/v1/query", json={"query": ""})

    assert response.status_code == 422
