"""
CrewAI Multi-Agent Orchestration with Neo4j Knowledge Graph, NAMS Memory, and MCP.

Defines three specialized collaborating agents:
1. KnowledgeGraphResearcher: Queries Neo4j for company profiles, leadership, and sector data.
2. MarketAndGraphAnalyst: Analyzes multi-hop graph relationships, supply chain connections, and market positioning.
3. ExecutiveReportWriter: Synthesizes findings, recalls user preferences from NAMS, and produces actionable executive reports.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool

from agent.custom_tools import get_custom_tools
from agent.mcp import is_mcp_enabled, load_mcp_tools
from agent.memory import get_memory_tools
from agent.tools import (
    CompanyProfileTool,
    CompanyRelationshipsTool,
    ListIndustriesTool,
    RunCypherQueryTool,
    SearchCompaniesTool,
    get_neo4j_tools,
)

logger = logging.getLogger(__name__)


def create_researcher_agent(tools: list[BaseTool] | None = None) -> Agent:
    """Agent specialized in exploring the Neo4j Knowledge Graph and gathering verified facts."""
    agent_tools = tools or [
        SearchCompaniesTool(),
        CompanyProfileTool(),
        ListIndustriesTool(),
    ]
    return Agent(
        role="Lead Knowledge Graph Researcher",
        goal="Discover ground-truth facts, entity metadata, and leadership structures from the Neo4j Knowledge Graph.",
        backstory=(
            "You are an expert investigative researcher specialized in graph databases and knowledge graphs. "
            "You query the Neo4j database to extract accurate, verified information about companies, executive leadership, "
            "and industry classifications without hallucinating. Always ground your claims in graph query results."
        ),
        tools=agent_tools,
        verbose=os.environ.get("CREW_VERBOSE", "true").lower() == "true",
        allow_delegation=False,
    )


def create_analyst_agent(tools: list[BaseTool] | None = None) -> Agent:
    """Agent specialized in traversing graph paths, identifying strategic relationships and risks."""
    agent_tools = tools or [
        CompanyRelationshipsTool(),
        RunCypherQueryTool(),
    ]
    return Agent(
        role="Strategic Market & Graph Analyst",
        goal="Analyze deep graph connections, investor/partner networks, and strategic positioning across the ecosystem.",
        backstory=(
            "You are a seasoned enterprise analyst who specializes in network analysis and corporate relationships. "
            "You analyze multi-hop graph patterns, co-investor ties, subsidiary networks, and competitive clusters "
            "in the Neo4j Knowledge Graph to uncover non-obvious market dynamics and strategic risks."
        ),
        tools=agent_tools,
        verbose=os.environ.get("CREW_VERBOSE", "true").lower() == "true",
        allow_delegation=False,
    )


def create_writer_agent(tools: list[BaseTool] | None = None) -> Agent:
    """Agent specialized in synthesizing intelligence into structured executive reports with memory recall."""
    agent_tools = tools or get_memory_tools()
    return Agent(
        role="Executive Intelligence Briefing Author",
        goal="Synthesize research and graph analysis into crisp, structured, decision-grade executive briefs.",
        backstory=(
            "You are an elite corporate communications and investment strategist. You take raw graph research "
            "and network analysis and turn them into structured, executive-ready intelligence briefings. "
            "You adapt your output to user preferences stored in long-term memory and format findings cleanly in Markdown."
        ),
        tools=agent_tools,
        verbose=os.environ.get("CREW_VERBOSE", "true").lower() == "true",
        allow_delegation=False,
    )


def create_query_agent(tools: list[BaseTool]) -> Agent:
    """Create an agent that answers an open-ended graph intelligence request."""
    return Agent(
        role="Neo4j Graph Intelligence Assistant",
        goal="Answer user questions accurately using the Neo4j knowledge graph and available MCP tools.",
        backstory=(
            "You are a precise graph intelligence assistant. You use available tools to retrieve facts "
            "before answering, distinguish verified results from inferences, and never claim data that "
            "is not returned by a tool."
        ),
        tools=tools,
        verbose=os.environ.get("CREW_VERBOSE", "true").lower() == "true",
        allow_delegation=False,
    )


def create_query_task(agent: Agent, query: str) -> Task:
    """Create a task that answers a normal-language user query."""
    return Task(
        description=(
            "Answer the following user request using the available Neo4j and MCP tools when needed. "
            "Use only verified tool results for factual claims, and state clearly if the graph does not "
            f"contain enough information.\n\nUser request: {query}"
        ),
        expected_output="A concise, accurate Markdown response that directly answers the user request.",
        agent=agent,
    )


def create_research_task(agent: Agent, company_name: str) -> Task:
    """Task for gathering initial company profile and leadership data from Neo4j."""
    return Task(
        description=(
            f"Search the Neo4j Knowledge Graph for '{company_name}'. "
            "Retrieve its company overview, industry categories, headquarters and operating locations, "
            "and all key executives/board members. Provide a clear summary of all extracted facts."
        ),
        expected_output=(
            "A structured markdown summary containing company name, description, industry categories, "
            "locations, and leadership roster with verified names and roles."
        ),
        agent=agent,
    )


def create_analysis_task(agent: Agent, company_name: str) -> Task:
    """Task for traversing graph connections and evaluating ecosystem relationships."""
    return Task(
        description=(
            f"Analyze the relationship network and graph topology for '{company_name}' in Neo4j. "
            "Traverse 1-2 hops of relationships to identify key partner organizations, related entities, "
            "and structural positioning. Highlight any strategic dependencies or significant graph clusters."
        ),
        expected_output=(
            "A detailed network analysis detailing connected entities, relationship types, network depth, "
            "and strategic insights derived from the graph paths."
        ),
        agent=agent,
    )


def create_report_task(agent: Agent, company_name: str, output_file: str | None = None) -> Task:
    """Task for producing the final executive briefing and saving key findings to NAMS memory."""
    task_kwargs: dict[str, Any] = {
        "description": (
            f"Using the findings from the research and analysis phases for '{company_name}', "
            "produce a comprehensive, executive-level intelligence briefing in Markdown format.\n"
            "Include sections: Executive Summary, Company Overview & Leadership, Graph Network & Ecosystem Analysis, "
            "Strategic Implications, and Key Takeaways.\n"
            "If memory tools are available, recall any user formatting preferences and save the key analytical findings "
            "as verified memory facts."
        ),
        "expected_output": (
            "A complete, professional Executive Intelligence Briefing formatted in clean Markdown with clear sections, "
            "bullet points, and actionable takeaways."
        ),
        "agent": agent,
    }
    if output_file:
        task_kwargs["output_file"] = output_file
    return Task(**task_kwargs)


def build_company_intelligence_crew(
    company_name: str,
    output_file: str | None = None,
    crew_id: str | None = None,
) -> Crew:
    """Assemble and configure the full multi-agent Crew for company intelligence."""
    memory_tools = get_memory_tools()
    mcp_tools = load_mcp_tools() if is_mcp_enabled() else []

    # Aura Graph Analytics can reject direct-driver routing discovery. Prefer
    # the local MCP transport when configured, matching the notebook workflow.
    graph_tools = mcp_tools or [
        SearchCompaniesTool(),
        CompanyProfileTool(),
        ListIndustriesTool(),
        CompanyRelationshipsTool(),
        RunCypherQueryTool(),
    ]
    researcher_tools = graph_tools + memory_tools
    analyst_tools = graph_tools + memory_tools

    writer_tools = list(memory_tools)

    researcher = create_researcher_agent(tools=researcher_tools)
    analyst = create_analyst_agent(tools=analyst_tools)
    writer = create_writer_agent(tools=writer_tools)

    task_research = create_research_task(researcher, company_name)
    task_analysis = create_analysis_task(analyst, company_name)
    task_report = create_report_task(writer, company_name, output_file=output_file)

    crew_kwargs: dict[str, Any] = {
        "agents": [researcher, analyst, writer],
        "tasks": [task_research, task_analysis, task_report],
        "process": Process.sequential,
        "verbose": os.environ.get("CREW_VERBOSE", "true").lower() == "true",
    }
    return Crew(**crew_kwargs)


def build_query_crew(query: str) -> Crew:
    """Build a single-agent crew for an open-ended natural-language query."""
    tools = get_memory_tools()
    if is_mcp_enabled():
        tools.extend(load_mcp_tools())
    else:
        tools.extend(get_neo4j_tools())
    tools.extend(get_custom_tools())

    agent = create_query_agent(tools)
    crew_kwargs: dict[str, Any] = {
        "agents": [agent],
        "tasks": [create_query_task(agent, query)],
        "process": Process.sequential,
        "verbose": os.environ.get("CREW_VERBOSE", "true").lower() == "true",
    }
    return Crew(**crew_kwargs)
