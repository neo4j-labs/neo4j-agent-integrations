"""Custom Python tool for the watsonx Orchestrate Neo4j agent.

Exposes a single curated graph query as an agent tool, alongside the
generic Cypher tools provided by the Neo4j MCP server.
"""

import json
import logging
import os

from ibm_watsonx_orchestrate.agent_builder.tools import tool
from neo4j import GraphDatabase

logging.basicConfig(level=logging.INFO)

APP_ID = "neo4j_local_creds"


def _config() -> dict:
    """Read Neo4j connection settings.

    Prefers the Orchestrate connection bound to this tool; falls back to
    environment variables so the file can also be run locally for testing.
    """
    try:
        from ibm_watsonx_orchestrate.run import connections

        conn = connections.key_value(APP_ID)
        return {
            "uri": conn["NEO4J_URI"],
            "username": conn["NEO4J_USERNAME"],
            "password": conn["NEO4J_PASSWORD"],
            "database": conn.get("NEO4J_DATABASE", "neo4j"),
        }
    except Exception as exc:  # noqa: BLE001 - fall back to env vars
        logging.warning("Connection '%s' unavailable (%s); using env vars.", APP_ID, exc)
        return {
            "uri": os.environ.get("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com:7687"),
            "username": os.environ.get("NEO4J_USERNAME", "companies"),
            "password": os.environ.get("NEO4J_PASSWORD", "companies"),
            "database": os.environ.get("NEO4J_DATABASE", "companies"),
        }


QUERY = """
MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
WHERE toLower(o.name) CONTAINS toLower($company)
RETURN o.name AS company,
       i.id AS investor_id,
       i.name AS investor_name,
       head(labels(i)) AS investor_type
LIMIT 50
"""


@tool(expected_credentials=[{"app_id": APP_ID, "type": "key_value_creds"}])
def get_investments(company: str) -> str:
    """Look up the investors backing a company in the Neo4j knowledge graph.

    Use this tool for any question about investors, funding, backing, or who
    invested in a company. Prefer this over writing a raw Cypher query.

    Args:
        company (str): Name or partial name of the company, for example
            "Databricks" or "Neo4j".

    Returns:
        str: JSON list of investors, each with investor_id, investor_name and
            investor_type. Returns an empty list if the company is not found.
    """
    cfg = _config()
    try:
        with GraphDatabase.driver(cfg["uri"], auth=(cfg["username"], cfg["password"])) as driver:
            records, _, _ = driver.execute_query(
                QUERY,
                company=company,
                database_=cfg["database"],
            )
        results = [record.data() for record in records]
        if not results:
            return json.dumps({"message": f"No investors found for '{company}'."})
        return json.dumps(results, indent=2)
    except Exception as exc:  # noqa: BLE001 - surface a readable message to the agent
        logging.error("get_investments failed: %s", exc)
        return json.dumps({"error": f"Error fetching investments: {exc}"})
