"""
Bridges the A2A protocol with the Google ADK LlmAgent, handling the core agent logic.
"""
import logging
import base64
import math

# --- A2A SDK Imports ---
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

# --- Google ADK Imports ---
from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

# --- Local Imports ---
from ..core.config import (
    NEO4J_URI,
    NEO4J_DATABASE,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    MCP_URL,
    GEMINI_MODEL,
    TRACK_TOKEN_USAGE,
    current_user_identity,
    current_request_tokens
)
from .token_manager import TokenManager
from .custom_tools import create_investment_tool

def track_token_usage_callback(callback_context, llm_response, **kwargs):
    """Callback triggered by ADK after every internal Gemini API call."""
    
    metadata = getattr(llm_response, 'usage_metadata', None)
    if not metadata and hasattr(llm_response, 'model_response'):
        metadata = getattr(llm_response.model_response, 'usage_metadata', None)

    if metadata:
        turn_tokens = getattr(metadata, 'total_token_count', 0)
        
        if turn_tokens > 0:
            current_total = current_request_tokens.get()
            current_request_tokens.set(current_total + turn_tokens)
            logging.info(f"Internal Model Turn: Used {turn_tokens} tokens. (Running Total: {current_request_tokens.get()})")
            
    return None
        
class Neo4jADKExecutor(AgentExecutor):
    """Bridges the A2A protocol with the Google ADK LlmAgent."""

    def __init__(self):
        """Initializes shared services for the agent executor."""
        self.session_service = InMemorySessionService()
        self.artifact_service = InMemoryArtifactService()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Executes the agent task, handling user queries and tool integration."""
        user_id = current_user_identity.get()
        logging.info(f"Executing task for user: {user_id} (Context ID: {context.context_id})")

        token_manager = None
        if TRACK_TOKEN_USAGE:
            token_manager = TokenManager()
            if not token_manager.check_limit(user_id):
                await event_queue.enqueue_event(
                    new_agent_text_message("You have reached your daily token limit. Please try again tomorrow.")
                )
                token_manager.close()
                return

        
        try:
            current_request_tokens.set(0)
            encoded_creds = base64.b64encode(f"{NEO4J_USERNAME}:{NEO4J_PASSWORD}".encode()).decode()
            
            # Setup Tools
            mcp_tools = McpToolset(
                connection_params=StreamableHTTPConnectionParams(
                    url=MCP_URL,
                    headers={"Authorization": f"Basic {encoded_creds}"}
                )
            )
            custom_investment_tool = create_investment_tool(
                NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_URI, NEO4J_DATABASE
            )

            # Instantiate ADK Agent
            adk_agent = LlmAgent(
                model=GEMINI_MODEL,
                name="neo4j_explorer",
                instruction="""You are a graph database assistant.
                You have access to standard MCP Neo4j tools and a custom investment lookup tool.
                Always run 'get-schema' first if you are unfamiliar with the graph structure.
                If a user asks about investments, prioritize your specialized custom tool.""",
                tools=[mcp_tools, custom_investment_tool],
                after_model_callback=[track_token_usage_callback]
            )

            # Process User Query
            user_query = "".join(
                part.root.text
                for part in (context.message.parts or [])
                if hasattr(part.root, 'text')
            )
            logging.info(f"Received query: {user_query}")

            # Get or Create Session
            session_id = context.context_id or "default_session"
            session = await self.session_service.get_session(
                app_name="neo4j_a2a_app", user_id=user_id, session_id=session_id
            )
            if not session:
                session = await self.session_service.create_session(
                    session_id=session_id, state={}, app_name="neo4j_a2a_app", user_id=user_id
                )

            # Run the Agent
            runner = Runner(
                app_name="neo4j_a2a_app",
                agent=adk_agent,
                artifact_service=self.artifact_service,
                session_service=self.session_service,
            )

            total_response_text = ""
            content = types.Content(role='user', parts=[types.Part(text=user_query)])
            events_async = runner.run_async(session_id=session.id, user_id=user_id, new_message=content)

            async for event in events_async:
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text:
                            logging.info(f"Agent response part: {part.text}")
                            total_response_text += part.text
                            await event_queue.enqueue_event(new_agent_text_message(part.text))

            if TRACK_TOKEN_USAGE:
                # Update Token Usage
                exact_tokens = current_request_tokens.get()
                logging.info(f"Total tokens used for this request: {exact_tokens}")
                if exact_tokens == 0:
                    exact_tokens = math.ceil((len(user_query) + len(total_response_text)) / 4)
                    logging.info(f"No token metadata available. Estimated tokens based on text length: {exact_tokens}")
                token_manager.add_tokens(user_id, exact_tokens)
                logging.info(f"User {user_id} used approximately {exact_tokens} tokens.")

        except Exception as e:
            logging.error(f"ADK Execution Error: {e}", exc_info=True)
            await event_queue.enqueue_event(new_agent_text_message(f"An error occurred: {str(e)}"))
        finally:
            if token_manager:
                token_manager.close()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancels the agent task."""
        logging.warning(f"Cancel requested for context ID: {context.context_id}")
        raise NotImplementedError('Cancel not yet supported.')
