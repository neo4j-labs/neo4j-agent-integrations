"""Unit tests for CrewAI agent and crew orchestration."""
from __future__ import annotations

from agent.crew import (
    build_company_intelligence_crew,
    create_analyst_agent,
    create_report_task,
    create_research_task,
    create_researcher_agent,
    create_writer_agent,
)
from agent.tools import SearchCompaniesTool


def test_agent_creations():
    researcher = create_researcher_agent()
    assert researcher.role == "Lead Knowledge Graph Researcher"
    assert len(researcher.tools) > 0

    analyst = create_analyst_agent()
    assert analyst.role == "Strategic Market & Graph Analyst"
    assert len(analyst.tools) > 0

    writer = create_writer_agent()
    assert writer.role == "Executive Intelligence Briefing Author"


def test_tasks_creation():
    researcher = create_researcher_agent()
    analyst = create_analyst_agent()
    writer = create_writer_agent()

    t_res = create_research_task(researcher, "Google")
    assert "Google" in t_res.description

    t_ana = create_research_task(analyst, "Google")
    assert t_ana.agent == analyst

    t_rep = create_report_task(writer, "Google", output_file="test_report.md")
    assert "Google" in t_rep.description
    assert t_rep.output_file == "test_report.md"


def test_build_company_intelligence_crew():
    crew = build_company_intelligence_crew(
        company_name="Google",
        crew_id="test_crew_id",
    )
    assert len(crew.agents) == 3
    assert len(crew.tasks) == 3


def test_company_crew_prefers_mcp_tools(monkeypatch):
    mcp_tool = SearchCompaniesTool()
    monkeypatch.setattr("agent.crew.is_mcp_enabled", lambda: True)
    monkeypatch.setattr("agent.crew.load_mcp_tools", lambda: [mcp_tool])
    monkeypatch.setattr("agent.crew.get_memory_tools", list)

    crew = build_company_intelligence_crew(company_name="Google")

    assert crew.agents[0].tools == [mcp_tool]
    assert crew.agents[1].tools == [mcp_tool]
