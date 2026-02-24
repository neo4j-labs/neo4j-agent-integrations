import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import boto3
from fastmcp import FastMCP
from neo4j import Driver, GraphDatabase
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class Organization(BaseModel):
    """An organization node from the Neo4j knowledge graph."""
    name: str
    summary: str = ""
    revenue: float | None = None
    nbrEmployees: int | None = Field(default=None, alias="nbrEmployees")
    isPublic: bool = False
    isDissolved: bool = False
    motto: str = ""

    model_config = {"populate_by_name": True, "extra": "allow"}


class IndustryCategory(BaseModel):
    """An industry category node from the Neo4j knowledge graph."""
    name: str


class Article(BaseModel):
    """An article node from the Neo4j knowledge graph."""
    title: str
    author: str = ""
    date: datetime | None = None
    sentiment: float | None = None
    siteName: str = ""
    summary: str = ""

    model_config = {"extra": "allow"}

    @field_validator("date", mode="before")
    @classmethod
    def _coerce_neo4j_datetime(cls, v):
        if v is not None and not isinstance(v, datetime):
            return v.to_native()
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_neo4j_credentials() -> dict:
    """Fetch Neo4j connection credentials from AWS Secrets Manager."""
    secret_arn = os.environ.get("SECRET_ARN")
    if not secret_arn:
        raise RuntimeError("SECRET_ARN environment variable not set")

    session = boto3.session.Session()
    sm_client = session.client(service_name="secretsmanager")

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

driver: Driver | None = None
database: str = "neo4j"


@asynccontextmanager
async def lifespan(_app):
    """Load credentials, create the driver, and verify connectivity on startup;
    close the driver on shutdown."""
    global driver, database

    credentials = _load_neo4j_credentials()
    driver = GraphDatabase.driver(
        credentials["NEO4J_URI"],
        auth=(credentials["NEO4J_USERNAME"], credentials["NEO4J_PASSWORD"]),
    )
    database = credentials.get("NEO4J_DATABASE", "neo4j")

    driver.verify_connectivity()
    logger.info("Neo4j driver connected to %s", credentials["NEO4J_URI"])
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
def get_organizations(limit: int) -> list[Organization]:
    """Return up to `limit` organizations from the Neo4j knowledge graph.

    Each organization has properties such as name, summary, revenue,
    nbrEmployees, isPublic, isDissolved, and motto.
    """
    records, _, _ = driver.execute_query(
        "MATCH (n:Organization) RETURN n LIMIT $limit",
        {"limit": limit}, database_=database)
    return [Organization.model_validate(dict(record["n"])) for record in records]


@mcp.tool()
def get_industry_categories(limit: int) -> list[IndustryCategory]:
    """Return up to `limit` industry category names from the Neo4j knowledge graph."""
    records, _, _ = driver.execute_query(
        "MATCH (n:IndustryCategory) RETURN n.name LIMIT $limit",
        {"limit": limit}, database_=database)
    return [IndustryCategory(name=record["n.name"]) for record in records]


@mcp.tool()
def get_articles_by_organization(name: str) -> list[Article]:
    """Return articles that mention the given organization name.

    Each article has properties such as title, author, date, sentiment,
    siteName, and summary.
    """
    records, _, _ = driver.execute_query(
        "MATCH (n:Article)-[:MENTIONS]->(o:Organization) WHERE o.name = $name RETURN n",
        {"name": name}, database_=database)
    return [Article.model_validate(dict(record["n"])) for record in records]


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", stateless_http=True)
