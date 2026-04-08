"""Configuration settings for the application."""
import os
from dotenv import load_dotenv
import contextvars
from a2a.types import AgentCard, AgentSkill, AgentProvider, AgentCapabilities
load_dotenv()

current_request_tokens = contextvars.ContextVar("current_request_tokens", default=0)

TRACK_TOKEN_USAGE = os.environ.get("TRACK_TOKEN_USAGE", "false").lower() == "true"

TRACKING_NEO4J_URI = os.environ.get("TRACKING_NEO4J_URI")
TRACKING_NEO4J_USER = os.environ.get("TRACKING_NEO4J_USER")
TRACKING_NEO4J_PASS = os.environ.get("TRACKING_NEO4J_PASS")
DAILY_TOKEN_LIMIT = int(os.environ.get("DAILY_TOKEN_LIMIT", "50000"))

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
SERVICE_URL = os.environ.get("SERVICE_URL")
SETUP_URL = os.environ.get("SETUP_URL")
PROVIDER_URL = os.environ.get("PROVIDER_URL")
PROVIDER_ORGANIZATION = os.environ.get("PROVIDER_ORGANIZATION")
AGENT_ICON_URL = os.environ.get("AGENT_ICON_URL")
REDIRECT_URL = os.environ.get("REDIRECT_URL")

INTERNAL_SECRET_KEY = os.environ.get("INTERNAL_SECRET_KEY")
MARKETPLACE_PROVIDER_ID = os.environ.get("MARKETPLACE_PROVIDER_ID")
MARKETPLACE_CERTS_URL = "https://www.googleapis.com/robot/v1/metadata/x509/cloud-commerce-partner@system.gserviceaccount.com"
AGENTSPACE_SA_EMAIL = "cloud-agentspace@system.gserviceaccount.com"
GOOGLE_CERTS_URL = f"https://www.googleapis.com/service_accounts/v1/metadata/x509/{AGENTSPACE_SA_EMAIL}"

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
    name='Neo4j-Graph-Query-Agent',
    description=f'An autonomous agent that queries a Neo4j database using natural language and custom tools. ⚠️ IMPORTANT: Before chatting, you must link your database credentials at: {SETUP_URL}',
    url=SERVICE_URL,
    version='1.0.0',
    default_input_modes=['application/json'], 
    default_output_modes=['application/json'],
    provider= AgentProvider(
        organization=PROVIDER_ORGANIZATION,
        url=PROVIDER_URL
    ),
    capabilities=AgentCapabilities(
        streaming=True,
        extensions=[
            {
                "uri": "https://cloud.google.com/marketplace/docs/partners/ai-agents/setup-dcr",
                "params": {
                    "target_url": f"{SERVICE_URL}/dcr"
                    }
                }
            ]
        ),
    skills=[skill], 
    supports_authenticated_extended_card=False,
    iconUrl = AGENT_ICON_URL,
    security=[{"oauth2": ["marketplacescopes.read"]}],
    security_schemes={
        "oauth2": {
            "type": "oauth2",
            "flows": {
                "authorizationCode": {
                    "authorizationUrl": f"{SERVICE_URL}/auth/authorize",
                    "tokenUrl": f"{SERVICE_URL}/auth/token",
                    "refreshUrl": f"{SERVICE_URL}/auth/token",
                    "scopes": {
                        "marketplacescopes.read": "Access to agent via Marketplace entitlement"
                        }
                    }
                }
            }
        }
    )
