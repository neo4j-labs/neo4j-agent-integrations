"""Configuration settings for the application."""
import os
from dotenv import load_dotenv
import contextvars
from a2a.types import AgentCard, AgentSkill, AgentProvider, AgentCapabilities
load_dotenv()

current_user_identity = contextvars.ContextVar("current_user_identity", default="anonymous")
current_request_tokens = contextvars.ContextVar("current_request_tokens", default=0)

TRACK_TOKEN_USAGE = os.environ.get("TRACK_TOKEN_USAGE", "false").lower() == "true"

TRACKING_NEO4J_URI = os.environ.get("TRACKING_NEO4J_URI")
TRACKING_NEO4J_USER = os.environ.get("TRACKING_NEO4J_USER")
TRACKING_NEO4J_PASS = os.environ.get("TRACKING_NEO4J_PASS")
DAILY_TOKEN_LIMIT = int(os.environ.get("DAILY_TOKEN_LIMIT", "50000"))

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
SERVICE_URL = os.environ.get("SERVICE_URL")

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
GCP_LOCATION = os.environ.get("GCP_LOCATION")

AGENT_PROMPT = """
You are a Graph Database Assistant. Your goal is to translate user natural language into accurate Cypher queries, execute them, and explain the results.
Follow this strict execution workflow:
ENVIRONMENT DISCOVERY: Always execute 'get-schema' first if the graph structure, node labels, or relationship types are unknown for the current session. Do not guess the schema.
TOOL ROUTING: Evaluate the user's intent. If the query is related to specific investments or financial entities, you MUST prioritize your specialized custom investment tool over standard raw Cypher queries.
QUERY GENERATION: Write efficient, modern Cypher. Ensure best practices (e.g., correct alias usage, directed relationships, and proper aggregation).
ERROR REASONING & SELF-CORRECTION: If a tool execution returns a Neo4j database error (e.g., SyntaxError, EntityNotFound, alias mismatch), DO NOT blindly retry the same query. Read the exact error message, analyze the syntax failure step-by-step, write a corrected Cypher query, and execute the new version.
GRACEFUL FAILURE: If you fail to successfully retrieve the data after attempting to self-correct, stop querying. Explain the technical database limitation or syntax issue clearly to the user and ask them to clarify their request.

Respond to the user in a clean, concise, and professional manner based ONLY on the data returned by your tools.
Always use the tools to get information. Do not make assumptions or fabricate data that is not returned by the database.
"""

skill = AgentSkill(
    id='neo4j_graph_query',
    name='Graph Database Querying',
    description='Queries organizational data, investments, and entity relationships in Neo4j.',
    tags=['neo4j', 'database', 'graph', 'investments'],
    examples=['Show me the graph schema', 'What are the investments for Acme Corp?']
)

public_agent_card = AgentCard(
    name='Neo4j-Agent-Direct',
    description=f'Queries a Neo4j database using natural language.\n\n⚠️ IMPORTANT: Before chatting, you must link your database credentials at: {SERVICE_URL}/setup',
    url=SERVICE_URL,
    version='1.0.0',
    default_input_modes=['application/json'], 
    default_output_modes=['application/json'],
    capabilities=AgentCapabilities(streaming=True),
    provider= AgentProvider(
        organization="Neo4j",
        url="https://neo4j.com"
    ),
    skills=[skill], 
    supports_authenticated_extended_card=False,
    security=[{"oauth2": ["openid", "email"]}],
    security_schemes={
        "oauth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": "https://accounts.google.com/o/oauth2/v2/auth",
                    "tokenUrl": "https://oauth2.googleapis.com/token",
                    "refreshUrl": "https://oauth2.googleapis.com/token",
                    "scopes": {
                        "openid": "Associate you with your Google account",
                        "email": "View your email address"
                    }
                }
            }
        }
    }
    )