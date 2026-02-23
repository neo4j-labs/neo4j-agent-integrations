import json
import logging
import os
from contextlib import asynccontextmanager

import boto3
from fastmcp import FastMCP
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _region_from_arn(arn: str) -> str | None:
    """Return the region component from an ARN (or None)."""
    if not arn:
        return None
    parts = arn.split(":")
    # ARN format: arn:partition:service:region:account:resource
    return parts[3] if len(parts) > 3 and parts[3] else None


def _load_neo4j_credentials() -> dict:
    """Fetch Neo4j connection credentials from AWS Secrets Manager."""
    secret_arn = os.environ.get("SECRET_ARN")
    if not secret_arn:
        raise RuntimeError("SECRET_ARN environment variable not set")

    region = _region_from_arn(secret_arn) or os.environ.get("AWS_REGION", "us-east-1")

    session = boto3.session.Session()
    sm_client = session.client(service_name="secretsmanager", region_name=region)

    secret_response = sm_client.get_secret_value(SecretId=secret_arn)
    secret_json: dict = json.loads(secret_response["SecretString"])

    # Validate required keys
    for key in ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD"):
        if not secret_json.get(key):
            raise RuntimeError(f"Secret is missing required key: {key}")

    return secret_json


# ---------------------------------------------------------------------------
# Driver lifecycle
# ---------------------------------------------------------------------------

_credentials = _load_neo4j_credentials()

driver = GraphDatabase.driver(
    _credentials["NEO4J_URI"],
    auth=(_credentials["NEO4J_USERNAME"], _credentials["NEO4J_PASSWORD"]),
)
database = _credentials.get("NEO4J_DATABASE", "neo4j")


@asynccontextmanager
async def lifespan(_app):
    """Verify connectivity on startup; close the driver on shutdown."""
    driver.verify_connectivity()
    logger.info("Neo4j driver connected to %s", _credentials["NEO4J_URI"])
    try:
        yield
    finally:
        driver.close()
        logger.info("Neo4j driver closed")


# ---------------------------------------------------------------------------
# MCP server & tools
# ---------------------------------------------------------------------------

mcp = FastMCP(lifespan=lifespan)


@mcp.tool()
def get_organizations(limit: int) -> list[dict]:
    """Return up to `limit` organizations from the Neo4j database as a list of dictionaries."""

    query = "MATCH (n:Organization) RETURN n LIMIT $limit"
    records, _, _ = driver.execute_query(query_=query, parameters_={"limit": limit}, database_=database)
    return [record.data() for record in records]


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", stateless_http=True)
