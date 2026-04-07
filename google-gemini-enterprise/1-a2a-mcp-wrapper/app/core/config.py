"""Configuration settings for the application."""
import os
from dotenv import load_dotenv
import contextvars
from a2a.types import AgentCard, AgentSkill, AgentCapabilities

load_dotenv()

current_user_identity = contextvars.ContextVar("current_user_identity", default="anonymous")
current_request_tokens = contextvars.ContextVar("current_request_tokens", default=0)

TRACK_TOKEN_USAGE = os.environ.get("TRACK_TOKEN_USAGE", "false").lower() == "true"

TRACKING_NEO4J_URI = os.environ.get("TRACKING_NEO4J_URI")
TRACKING_NEO4J_USER = os.environ.get("TRACKING_NEO4J_USER")
TRACKING_NEO4J_PASS = os.environ.get("TRACKING_NEO4J_PASS")
DAILY_TOKEN_LIMIT = int(os.environ.get("DAILY_TOKEN_LIMIT", "50000"))

NEO4J_URI = os.environ.get("NEO4J_URI")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
NEO4J_USERNAME = os.environ.get("NEO4J_USERNAME")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD")

MCP_URL = os.environ.get("MCP_URL")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
SERVICE_URL = os.environ.get("SERVICE_URL")

skill = AgentSkill(
    id='neo4j_graph_query',
    name='Graph Database Querying',
    description='Queries organizational data, investments, and entity relationships in Neo4j.',
    tags=['neo4j', 'database', 'graph', 'investments'],
    examples=['Show me the graph schema', 'What are the investments for Acme Corp?']
)

public_agent_card = AgentCard(
    name='Neo4j-Graph-Query-Agent',
    description='An autonomous agent that queries a Neo4j database using natural language and custom tools.',
    url=SERVICE_URL,
    version='1.0.0',
    default_input_modes=['text/plain'],
    default_output_modes=['text/plain'],
    capabilities=AgentCapabilities(streaming=True),
    skills=[skill],
    supports_authenticated_extended_card=True
)
