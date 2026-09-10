"""
Production FastAPI Application for CrewAI + Neo4j Agent Integrations.

Provides REST API endpoints to trigger and monitor multi-agent crew runs,
suitable for deployment in cloud environments, Docker containers, and enterprise stacks.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from agent.crew import build_company_intelligence_crew, build_query_crew

app = FastAPI(
    title="CrewAI + Neo4j Multi-Agent Intelligence API",
    description="REST API for triggering and executing multi-agent graph intelligence workflows.",
    version="0.1.0",
)
STATIC_DIRECTORY = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")


class ResearchRequest(BaseModel):
    company_name: str = Field(..., description="Company name to analyze in Neo4j Knowledge Graph.")
    crew_id: str | None = Field(default=None, description="Optional unique session ID for NAMS memory.")
    output_file: str | None = Field(default=None, description="Optional path to persist report markdown.")


class ResearchResponse(BaseModel):
    company_name: str
    status: str
    result: str


class QueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language question or request for the graph intelligence assistant.",
    )
class QueryResponse(BaseModel):
    query: str
    status: str
    result: str


@app.get("/", include_in_schema=False)
def chat_interface() -> FileResponse:
    """Serve the browser chat interface."""
    return FileResponse(STATIC_DIRECTORY / "index.html")


@app.get("/health")
def health_check() -> dict[str, Any]:
    """Service health and component status check."""
    return {
        "status": "healthy",
        "neo4j_configured": bool(os.environ.get("NEO4J_URI")),
        "memory_configured": bool(os.environ.get("MEMORY_API_KEY")),
        "mcp_configured": bool(os.environ.get("MCP_SERVER_COMMAND")),
    }


@app.post("/api/v1/research", response_model=ResearchResponse)
def run_research(request: ResearchRequest) -> dict[str, Any]:
    """Trigger a synchronous multi-agent Crew run and return the executive brief."""
    crew = build_company_intelligence_crew(
        company_name=request.company_name,
        output_file=request.output_file,
        crew_id=request.crew_id,
    )
    result = crew.kickoff()
    return {
        "company_name": request.company_name,
        "status": "completed",
        "result": str(result),
    }


@app.post("/api/v1/query", response_model=QueryResponse)
def run_query(request: QueryRequest) -> dict[str, str]:
    """Answer an open-ended natural-language request with graph and MCP tools."""
    crew = build_query_crew(query=request.query)
    result = crew.kickoff()
    return {
        "query": request.query,
        "status": "completed",
        "result": str(result),
    }
