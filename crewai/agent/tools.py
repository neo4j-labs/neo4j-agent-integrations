"""
Neo4j Knowledge Graph Tools for CrewAI.

Provides custom CrewAI tools (subclassing BaseTool) to query the Neo4j
Companies knowledge graph safely using parameterized Cypher, full-text index
search, entity relationships, and executive leadership queries.
"""
from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from neo4j import GraphDatabase, Driver
    _HAS_NEO4J = True
except ImportError:
    _HAS_NEO4J = False
    GraphDatabase = None  # type: ignore[assignment,misc]
    Driver = None  # type: ignore[assignment,misc]


@lru_cache(maxsize=1)
def get_driver() -> Any:
    """Initialize and cache the Neo4j driver using environment variables."""
    if not _HAS_NEO4J:
        raise ImportError(
            "neo4j Python package is required. Install with: pip install neo4j"
        )
    uri = os.environ.get("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com:7687")
    username = os.environ.get("NEO4J_USERNAME", "companies")
    password = os.environ.get("NEO4J_PASSWORD", "companies")
    return GraphDatabase.driver(uri, auth=(username, password))


def execute_cypher(query: str, params: dict[str, Any] | None = None, database: str | None = None) -> list[dict[str, Any]]:
    """Execute a parameterized Cypher query and return results as a list of dicts.

    All user-supplied inputs must be passed via ``params`` to prevent Cypher injection.
    """
    driver = get_driver()
    db = database or os.environ.get("NEO4J_DATABASE", "companies")
    try:
        records, summary, keys = driver.execute_query(
            query,
            parameters_=params or {},
            database_=db,
        )
        return [record.data() for record in records]
    except Exception as e:
        logger.error(f"Error executing Cypher query: {e}")
        return [{"error": str(e), "query": query}]


# ── Tool 1: Search Companies Tool ─────────────────────────────────────────────

class SearchCompaniesInput(BaseModel):
    """Input schema for SearchCompaniesTool."""
    search: str = Field(..., description="Company name or keyword to search for.")
    limit: int = Field(default=10, description="Maximum number of results to return (1-50).")


class SearchCompaniesTool(BaseTool):
    name: str = "search_companies"
    description: str = (
        "Full-text search for companies in the Neo4j knowledge graph by name or keyword. "
        "Returns company id, name, summary, and relevance score."
    )
    args_schema: Type[BaseModel] = SearchCompaniesInput

    def _run(self, search: str, limit: int = 10) -> str:
        safe_limit = max(1, min(int(limit), 50))
        query = """
            CALL db.index.fulltext.queryNodes('entity', $search, {limit: $limit})
            YIELD node AS c, score
            WHERE c:Organization
            RETURN c.id AS company_id, c.name AS name, c.summary AS summary, score
            ORDER BY score DESC
        """
        results = execute_cypher(query, {"search": search, "limit": safe_limit})
        if not results:
            # Fallback to case-insensitive CONTAINS search
            fallback_query = """
                MATCH (c:Organization)
                WHERE toLower(c.name) CONTAINS toLower($search)
                RETURN c.id AS company_id, c.name AS name, c.summary AS summary, 1.0 AS score
                LIMIT $limit
            """
            results = execute_cypher(fallback_query, {"search": search, "limit": safe_limit})
        return json.dumps(results, indent=2)


# ── Tool 2: Company Profile Tool ──────────────────────────────────────────────

class CompanyProfileInput(BaseModel):
    """Input schema for CompanyProfileTool."""
    company_name: str = Field(..., description="Company name to look up (exact or partial match).")


class CompanyProfileTool(BaseTool):
    name: str = "query_company_profile"
    description: str = (
        "Fetch a comprehensive company profile from the Neo4j knowledge graph including "
        "summary, industry categories, headquarters/operating locations, and executive leadership."
    )
    args_schema: Type[BaseModel] = CompanyProfileInput

    def _run(self, company_name: str) -> str:
        query = """
            MATCH (o:Organization)
            WHERE toLower(o.name) CONTAINS toLower($company_name)
            OPTIONAL MATCH (o)-[:HAS_CATEGORY]->(c:IndustryCategory)
            OPTIONAL MATCH (o)-[:IN_CITY]->(city:City)
            OPTIONAL MATCH (city)-[:IN_COUNTRY]->(country:Country)
            OPTIONAL MATCH (o)-[:HAS_CEO]->(ceo:Person)
            OPTIONAL MATCH (o)-[:HAS_BOARD_MEMBER]->(board:Person)
            RETURN o.id AS company_id, o.name AS name, o.summary AS summary,
                   collect(DISTINCT c.name)[..5] AS industries,
                   collect(DISTINCT city.name)[..3] + collect(DISTINCT country.name)[..3] AS locations,
                   [p IN collect(DISTINCT {name: ceo.name, title: 'CEO'})
                          + collect(DISTINCT {name: board.name, title: 'Board Member'})
                    WHERE p.name IS NOT NULL][..8] AS leadership
            LIMIT 1
        """
        results = execute_cypher(query, {"company_name": company_name})
        if not results:
            return json.dumps({"error": f"No company profile found matching '{company_name}'"})
        return json.dumps(results[0], indent=2)


# ── Tool 3: Company Relationships Tool ────────────────────────────────────────

class CompanyRelationshipsInput(BaseModel):
    """Input schema for CompanyRelationshipsTool."""
    company_name: str = Field(..., description="Exact company name to explore connections for.")
    max_depth: int = Field(default=2, description="Graph traversal depth (1 to 3 hops).")


class CompanyRelationshipsTool(BaseTool):
    name: str = "analyze_company_relationships"
    description: str = (
        "Traverse the Neo4j graph to find connected organizations, investors, subsidiaries, "
        "and related partners up to N hops away."
    )
    args_schema: Type[BaseModel] = CompanyRelationshipsInput

    def _run(self, company_name: str, max_depth: int = 2) -> str:
        depth = max(1, min(int(max_depth), 3))
        query = f"""
            MATCH path = (o1:Organization {{name: $company_name}})-[*1..{depth}]-(o2:Organization)
            WHERE o1 <> o2
            RETURN DISTINCT o2.id AS company_id, o2.name AS organization,
                   [rel IN relationships(path) | type(rel)] AS relationship_types,
                   length(path) AS distance
            ORDER BY distance, organization
            LIMIT 20
        """
        results = execute_cypher(query, {"company_name": company_name})
        if not results:
            return json.dumps({"message": f"No direct relationships found for '{company_name}' within {depth} hops."})
        return json.dumps(results, indent=2)


# ── Tool 4: Cypher Query Tool ─────────────────────────────────────────────────

class CypherQueryInput(BaseModel):
    """Input schema for RunCypherQueryTool."""
    query: str = Field(..., description="Valid Cypher query to execute against Neo4j.")


class RunCypherQueryTool(BaseTool):
    name: str = "run_cypher_query"
    description: str = (
        "Execute a raw Cypher query against the Neo4j knowledge graph. "
        "Use this for custom aggregations, specific relationship path patterns, or complex queries."
    )
    args_schema: Type[BaseModel] = CypherQueryInput

    def _run(self, query: str) -> str:
        # Prevent harmful write/delete statements when operating in read mode
        forbidden = ["CREATE", "DELETE", "DETACH", "DROP", "REMOVE", "SET", "MERGE"]
        upper = query.upper()
        for word in forbidden:
            # Check for standalone keywords
            if f" {word} " in f" {upper} ":
                return json.dumps({"error": f"Write operations like '{word}' are forbidden in query tool."})
        results = execute_cypher(query)
        return json.dumps(results, indent=2)


# ── Tool 5: Industry Categories Tool ──────────────────────────────────────────

class ListIndustriesInput(BaseModel):
    """Input schema for ListIndustriesTool."""
    limit: int = Field(default=30, description="Max categories to return.")


class ListIndustriesTool(BaseTool):
    name: str = "list_industry_categories"
    description: str = "List available industry sectors and categories in the Neo4j knowledge graph."
    args_schema: Type[BaseModel] = ListIndustriesInput

    def _run(self, limit: int = 30) -> str:
        safe_limit = max(1, min(int(limit), 100))
        query = "MATCH (i:IndustryCategory) RETURN i.name AS industry ORDER BY industry LIMIT $limit"
        results = execute_cypher(query, {"limit": safe_limit})
        return json.dumps(results, indent=2)


def get_neo4j_tools() -> list[BaseTool]:
    """Return all standard Neo4j Knowledge Graph tools for CrewAI agents."""
    return [
        SearchCompaniesTool(),
        CompanyProfileTool(),
        CompanyRelationshipsTool(),
        RunCypherQueryTool(),
        ListIndustriesTool(),
    ]
