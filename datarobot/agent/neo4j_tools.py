"""
LangChain-compatible Neo4j tools for the companies knowledge graph.

These tools follow the DataRobot `datarobot-agent-application` template pattern
and are designed for use with dr-genai / dr-agent runtimes via LangGraph.
They can also be used standalone for local testing.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field

try:
    from langchain_neo4j import Neo4jGraph
    _NEO4J_GRAPH_AVAILABLE = True
except ImportError:
    _NEO4J_GRAPH_AVAILABLE = False
    Neo4jGraph = None  # type: ignore[assignment,misc]


@lru_cache(maxsize=1)
def _get_graph():
    if not _NEO4J_GRAPH_AVAILABLE:
        raise ImportError(
            "langchain-neo4j is required. Install with: pip install langchain-neo4j"
        )
    return Neo4jGraph(
        url=os.environ.get("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com:7687"),
        username=os.environ.get("NEO4J_USERNAME", "companies"),
        password=os.environ.get("NEO4J_PASSWORD", ""),
        database=os.environ.get("NEO4J_DATABASE", "companies"),
    )


def _run_query(query: str, params: dict | None = None) -> str:
    """Execute a parameterized Cypher query and format the result as a string.

    All values from tool arguments must be passed via ``params`` (Neo4j
    parameter placeholders, e.g. ``$search``) rather than interpolated into
    the query text, to avoid Cypher injection.
    """
    try:
        graph = _get_graph()
        result = graph.query(query, params=params or {})
        if not result:
            return "No data found for this query."
        return str(result)
    except Exception as e:
        return f"Query error: {e}. Check your Cypher syntax and node labels."


@tool
def run_cypher_query(
    cypher_query: Annotated[str, Field(description="A valid Cypher query to run against the Neo4j knowledge graph.")],
) -> str:
    """Execute a Cypher query against the Neo4j companies knowledge graph and return results."""
    return _run_query(cypher_query)


@tool
def search_companies(
    search: Annotated[str, Field(description="Company name search text (partial name or keyword).")],
    limit: Annotated[int, Field(description="Maximum results to return.")] = 10,
) -> str:
    """Full-text search for companies in the Neo4j knowledge graph by name or keyword."""
    safe_limit = max(1, min(int(limit), 100))
    query = """
        CALL db.index.fulltext.queryNodes('entity', $search, {limit: $limit})
        YIELD node AS c, score
        WHERE c:Organization
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary, score
        ORDER BY score DESC
    """
    return _run_query(query, {"search": search, "limit": safe_limit})


@tool
def query_company_profile(
    company_name: Annotated[str, Field(description="Company name to look up (exact or approximate).")],
) -> str:
    """Fetch a company profile including summary, industries, locations, and leadership from Neo4j."""
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
    return _run_query(query, {"company_name": company_name})


@tool
def list_industries(
    limit: Annotated[int, Field(description="Maximum number of industry categories to return.")] = 50,
) -> str:
    """List all industry categories available in the Neo4j knowledge graph."""
    safe_limit = max(1, min(int(limit), 500))
    query = "MATCH (i:IndustryCategory) RETURN i.name AS industry ORDER BY industry LIMIT $limit"
    return _run_query(query, {"limit": safe_limit})


@tool
def companies_in_industry(
    industry: Annotated[str, Field(description="Exact industry category name (use list_industries first).")],
) -> str:
    """Find companies that belong to a specific industry category in Neo4j."""
    query = """
        MATCH (:IndustryCategory {name: $industry})<-[:HAS_CATEGORY]-(c:Organization)
        RETURN c.id AS company_id, c.name AS name, c.summary AS summary
        ORDER BY c.name LIMIT 10
    """
    return _run_query(query, {"industry": industry})


@tool
def analyze_company_relationships(
    company_name: Annotated[str, Field(description="Exact company name to explore.")],
    max_depth: Annotated[int, Field(description="Graph traversal depth (1-4).")] = 2,
) -> str:
    """Explore organization-to-organization relationships (subsidiaries, investors, competitors) in Neo4j."""
    # Variable-length relationship hop counts cannot be parameterized in Cypher,
    # so the depth is validated and coerced to a bounded int before interpolation.
    depth = max(1, min(int(max_depth), 4))
    query = f"""
        MATCH path = (o1:Organization {{name: $company_name}})-[*1..{depth}]-(o2:Organization)
        WHERE o1 <> o2
        RETURN DISTINCT o2.id AS company_id, o2.name AS organization,
               [rel IN relationships(path) | type(rel)] AS relationships,
               length(path) AS distance
        ORDER BY distance, organization LIMIT 20
    """
    return _run_query(query, {"company_name": company_name})


@tool
def people_at_company(
    company_id: Annotated[str, Field(description="Internal company_id from search_companies or query_company_profile.")],
) -> str:
    """List executives and board members at a company by its internal company_id."""
    query = """
        MATCH (c:Organization {id: $company_id})-[role]-(p:Person)
        RETURN replace(type(role), 'HAS_', '') AS role,
               p.name AS person_name, c.id AS company_id, c.name AS company_name
        ORDER BY role, person_name
    """
    return _run_query(query, {"company_id": company_id})


def get_all_tools() -> list:
    """Return all Neo4j LangChain tools for registration in a DataRobot agent."""
    return [
        run_cypher_query,
        search_companies,
        query_company_profile,
        list_industries,
        companies_in_industry,
        analyze_company_relationships,
        people_at_company,
    ]
