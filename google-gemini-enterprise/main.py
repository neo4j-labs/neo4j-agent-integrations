import os
import json
import logging
import uvicorn
from dotenv import load_dotenv
from neo4j import GraphDatabase

# --- A2A SDK Imports ---
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from a2a.utils import new_agent_text_message

# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
# Notice the new Stdio imports and FunctionTool
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.mcp_tool import McpToolset

from mcp import StdioServerParameters
import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Custom Python Tool ---
async def get_investments(company: str) -> str:
    """
    Returns the investments by a company by name. 
    Returns a list of investment ids, names, and types.
    """
    query = """
    MATCH (o:Organization)-[:HAS_INVESTOR]->(i)
    WHERE o.name = $company
    RETURN i.id as id, i.name as name, head(labels(i)) as type
    """
    try:
        driver = GraphDatabase.driver(
            os.environ["NEO4J_URI"], 
            auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"])
        )
        # Note: The Neo4j driver requires the database argument here as 'database_'
        records, _, _ = driver.execute_query(
            query, 
            company=company,
            database_=os.environ.get("NEO4J_DATABASE", "neo4j")
        )
        driver.close()

        results = [record.data() for record in records]
        return json.dumps(results, indent=2)
    except Exception as e:
        logging.error(f"Error executing custom tool: {e}")
        return f"Error fetching investments: {str(e)}"



# --- A2A Executor ---
class Neo4jADKExecutor(AgentExecutor):
    """Bridges the official A2A protocol with the Google ADK LlmAgent."""
    def __init__(self):
        # 1. Setup STDIO MCP Connection (Requires the binary in the Docker container)
        mcp_tools = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command='neo4j-mcp', 
                    args=[], 
                    env={
                        "NEO4J_URI": os.environ["NEO4J_URI"],
                        "NEO4J_USERNAME": os.environ["NEO4J_USERNAME"],
                        "NEO4J_PASSWORD": os.environ["NEO4J_PASSWORD"],
                        "NEO4J_DATABASE": os.environ.get("NEO4J_DATABASE", "neo4j"),
                        "NEO4J_READ_ONLY": "true"
                    }
                )
            )
        )

        # 2. Wrap the custom python function
        custom_investment_tool = FunctionTool(get_investments)

        # 3. Inject BOTH tools into the ADK Agent
        self.adk_agent = LlmAgent(
            model=os.environ.get("GEMINI_MODEL", "gemini-flash-latest"),
            name="neo4j_explorer",
            instruction="""You are a graph database assistant connected via A2A.
            You have access to standard MCP Neo4j tools and a custom investment lookup tool.
            Always run 'get-schema' first if you are unfamiliar with the graph structure.
            If a user asks about investments, prioritize your specialized custom tool.""",
            tools=[mcp_tools, custom_investment_tool]
        )

        self.session_service = InMemorySessionService()
        self.artifact_service = InMemoryArtifactService()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        logging.info(f"Executing task for context ID: {context.context_id}")
        user_query = ""
        if context.message and context.message.parts:
            for part in context.message.parts:
                if hasattr(part.root, 'text'):
                    user_query += part.root.text
        logging.info(f"Received query: {user_query}")

        session_id = context.context_id or "default_session"
        session = await self.session_service.get_session(
            app_name="neo4j_a2a_app",
            user_id="user_1",
            session_id=session_id
        )
        if not session:
            session = await self.session_service.create_session(
                session_id=session_id, state={}, app_name="neo4j_a2a_app", user_id="user_1"
            )

        runner = Runner(
            app_name="neo4j_a2a_app",
            agent=self.adk_agent,
            artifact_service=self.artifact_service,
            session_service=self.session_service,
        )

        try:
            content = types.Content(role='user', parts=[types.Part(text=user_query)])
            events_async = runner.run_async(session_id=session.id, user_id=session.user_id, new_message=content)

            async for event in events_async:
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text:
                            await event_queue.enqueue_event(new_agent_text_message(part.text))
        except Exception as e:
            logging.error(f"ADK Execution Error: {e}", exc_info=True)
            await event_queue.enqueue_event(new_agent_text_message(f"Error executing graph query: {str(e)}"))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise Exception('Cancel not supported.')



# --- Server Bootstrapping ---
skill = AgentSkill(
    id='neo4j_graph_query',
    name='Graph Database Querying',
    description='Queries organizational data, investments, and entity relationships in Neo4j.',
    tags=['neo4j', 'database', 'graph', 'investments'],
    examples=['Show me the graph schema', 'What are the investments for Acme Corp?']
)

public_agent_card = AgentCard(
    name='Neo4j-Secured',
    description='An autonomous agent that queries a Neo4j database using natural language and custom tools.',
    url=os.environ["SERVICE_URL"],
    version='1.0.0',
    default_input_modes=['text/plain'],
    default_output_modes=['text/plain'],
    capabilities=AgentCapabilities(streaming=True),
    skills=[skill],
    supports_authenticated_extended_card=True
)

request_handler = DefaultRequestHandler(
    agent_executor=Neo4jADKExecutor(),
    task_store=InMemoryTaskStore()
)

server = A2AStarletteApplication(
    agent_card=public_agent_card,
    http_handler=request_handler
)

app = server.build()

# --- NEW: OAuth 2.0 Validation Middleware ---
class OAuthValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logging.info(f"Incoming request: {request.method} {request.url.path}")
        
        # Allow open access for agent card discovery and health checks
        if request.url.path in ["/health", "/docs", "/.well-known/agent.json"]:
            return await call_next(request)
        
        if request.url.path == "/" and request.method == "GET":
            logging.info("Allowing unauthenticated access to root endpoint for agent card retrieval")
            return await call_next(request)
        
        logging.info("Validating Authorization header for incoming request")
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            logging.warning("Blocked request: Missing or invalid Authorization header")
            return JSONResponse({"error": "Missing or invalid Authorization header"}, status_code=401)

        token = auth_header.split(" ")[1]
        # Verify the access token with Google's tokeninfo endpoint
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?access_token={token}")

        logging.info(f"Token validation response status: {resp.status_code}")
        if resp.status_code != 200:
            logging.warning("Blocked request: Invalid OAuth token")
            return JSONResponse({"error": "Invalid OAuth access token"}, status_code=401)

        token_data = resp.json()
        logging.info(f"Authenticated request from client_id: {token_data.get('aud')}")

        return await call_next(request)

# Attach the security middleware to your app
app.add_middleware(OAuthValidationMiddleware)

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)