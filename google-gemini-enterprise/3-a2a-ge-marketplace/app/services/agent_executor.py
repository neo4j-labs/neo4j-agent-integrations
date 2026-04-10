"""
Bridges the A2A protocol with the Google ADK LlmAgent, handling the core agent logic.
"""
import logging
import base64
import math
import uuid 
import re

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.utils import new_agent_text_message

from google.genai import types
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.planners import BuiltInPlanner

from ..core.config import (
    GEMINI_MODEL,
    TRACK_TOKEN_USAGE,
    AGENT_PROMPT
)
from app.core.context import current_order_id, current_user_email, current_request_tokens
from .token_manager import TokenManager
from .custom_tools import get_tenant_tools

MAX_QUERY_LENGTH = 2000

def track_token_usage_callback(callback_context, llm_response, **kwargs):
    """Callback triggered by ADK after every internal Gemini API call."""
    logging.info("[agent_executor] track_token_usage_callback triggered")
    metadata = getattr(llm_response, 'usage_metadata', None)
    if not metadata and hasattr(llm_response, 'model_response'):
        metadata = getattr(llm_response.model_response, 'usage_metadata', None)

    if metadata:
        turn_tokens = getattr(metadata, 'total_token_count', 0)
        if turn_tokens > 0:
            current_total = current_request_tokens.get()
            current_request_tokens.set(current_total + turn_tokens)
            logging.info(f"[agent_executor] Internal Model Turn: Used {turn_tokens} tokens. (Running Total: {current_request_tokens.get()})")
    else:
        logging.info("[agent_executor] No usage_metadata found in llm_response")

    return None

def guardrail_check(query: str) -> bool:
    """
    OWASP-aligned prompt injection and Cypher injection defense.
    Returns True if the query is safe, False if it flags a security rule.
    """
    logging.info("[agent_executor] Performing guardrail check on query")
    malicious_patterns = [
        r"(?i)ignore\s+(all\s+)?previous\s+instructions",
        r"(?i)system\s+prompt",
        r"(?i)you\s+are\s+now",
        r"(?i)bypass\s+restrictions",
        r"(?i)forget\s+everything",
        r"(?i)act\s+as\s+(an\s+)?unrestricted",
        r"(?i)output\s+initialization",
        r"(?i)print\s+instructions",
        r"(?i)drop\s+database",
        r"(?i)delete\s+match",
        r"(?i)detach\s+delete",
        r"(?i)set\s+.*=",
        r"(?i)merge\s+\("
    ]

    for pattern in malicious_patterns:
        if re.search(pattern, query):
            logging.warning(f"[agent_executor] Guardrail triggered: Matched blocked pattern -> {pattern}")
            return False

    if len(query) > 0:
        special_char_count = sum(1 for c in query if not c.isalnum() and not c.isspace())
        special_char_ratio = special_char_count / len(query)

        if special_char_ratio > 0.3:
            logging.warning("[agent_executor] Guardrail triggered: Abnormally high concentration of special characters.")
            return False

    longest_word = max((len(word) for word in query.split()), default=0)
    if longest_word > 50: 
        logging.warning(f"[agent_executor] Guardrail triggered: Abnormally long single word detected ({longest_word} chars).")
        return False

    logging.info("[agent_executor] Guardrail check passed")
    return True

class Neo4jADKExecutor(AgentExecutor):
    """Bridges the A2A protocol with the Google ADK LlmAgent."""

    def __init__(self):
        """Initializes shared services for the agent executor."""
        logging.info("[agent_executor] Initializing Neo4jADKExecutor")
        self.session_service = InMemorySessionService()
        self.artifact_service = InMemoryArtifactService()
        logging.info("[agent_executor] Neo4jADKExecutor initialized")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Executes the agent task, handling user queries and tool integration."""
        order_id = current_order_id.get()
        user_email = current_user_email.get()

        logging.info(f"[agent_executor] Executing task for user: {user_email} under order: {order_id}")

        token_manager = TokenManager()

        try:
            if TRACK_TOKEN_USAGE:
                logging.info("[agent_executor] Token usage tracking is enabled")
                if not token_manager.check_limit(user_email, order_id):
                    logging.warning(f"[agent_executor] User {user_email} reached daily token limit.")
                    await event_queue.enqueue_event(
                        new_agent_text_message("You have reached your daily token limit. Please try again tomorrow.")
                    )
                    return

            current_request_tokens.set(0)
            logging.info("[agent_executor] Reset token counter for new request")

            user_query = "".join(
                part.root.text
                for part in (context.message.parts or [])
                if hasattr(part.root, 'text')
            ).strip()

            if not user_query:
                logging.warning("[agent_executor] Received an empty query.")
                await event_queue.enqueue_event(new_agent_text_message("Received an empty query."))
                return

            if len(user_query) > MAX_QUERY_LENGTH:
                logging.warning(f"[agent_executor] User {user_email} exceeded query length limit.")
                await event_queue.enqueue_event(
                    new_agent_text_message(f"Your query is too long. Please keep it under {MAX_QUERY_LENGTH} characters.")
                )
                return

            if not guardrail_check(user_query):
                logging.warning(f"[agent_executor] Security guardrail triggered for user {user_email}.")
                await event_queue.enqueue_event(
                    new_agent_text_message("I cannot process this request due to security policy restrictions.")
                )
                return

            logging.info(f"[agent_executor] Received safe query from {user_email}")

            creds = token_manager.get_user_credentials(order_id)
            if not creds:
                logging.error(f"[agent_executor] Credentials not found or account inactive for order {order_id}")
                await event_queue.enqueue_event(
                    new_agent_text_message("Error: Database connection not configured or account inactive. Please complete setup.")
                )
                return

            dynamic_user = creds["user"]
            dynamic_pass = creds["password"]
            dynamic_uri = creds["uri"]
            dynamic_db = creds.get("database", "neo4j")

            logging.info("[agent_executor] Setting up tools with tenant credentials")
            tenant_tools = get_tenant_tools(dynamic_user, dynamic_pass, dynamic_uri, dynamic_db)

            logging.info("[agent_executor] Instantiating ADK Agent")
            adk_agent = LlmAgent(
                model=GEMINI_MODEL,
                name="neo4j_explorer",
                instruction=AGENT_PROMPT,
                tools=tenant_tools,
                planner=BuiltInPlanner(
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False, 
                        thinking_budget=1024,
                    )
                ),
                after_model_callback=[track_token_usage_callback]
            )

            session_id = context.context_id
            if not session_id:
                session_id = f"session_{user_email}_{uuid.uuid4().hex}"

            session = await self.session_service.get_session(
                app_name="neo4j_a2a_app", user_id=user_email, session_id=session_id
            )

            if not session:
                session = await self.session_service.create_session(
                    session_id=session_id, state={}, app_name="neo4j_a2a_app", user_id=user_email
                )

            logging.info(f"[agent_executor] Running agent for session {session.id}")
            runner = Runner(
                app_name="neo4j_a2a_app",
                agent=adk_agent,
                artifact_service=self.artifact_service,
                session_service=self.session_service,
            )

            total_response_text = ""
            content = types.Content(role='user', parts=[types.Part(text=user_query)])
            events_async = runner.run_async(session_id=session.id, user_id=user_email, new_message=content)

            async for event in events_async:
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        if part.text:
                            total_response_text += part.text
                            await event_queue.enqueue_event(new_agent_text_message(part.text))

            logging.info(f"[agent_executor] Agent execution finished for session {session.id}.")

            if TRACK_TOKEN_USAGE:
                exact_tokens = current_request_tokens.get()
                if exact_tokens == 0:
                    exact_tokens = math.ceil((len(user_query) + len(total_response_text)) / 4)
                    logging.info(f"[agent_executor] No token metadata available. Estimated tokens: {exact_tokens}")

                token_manager.add_tokens(user_email, exact_tokens)
                logging.info(f"[agent_executor] User {user_email} used {exact_tokens} tokens.")

        except Exception as e:
            logging.error(f"[agent_executor] ADK Execution Error: {e}", exc_info=True)
            await event_queue.enqueue_event(new_agent_text_message("An unexpected error occurred while processing your request."))
        finally:
            logging.info(f"[agent_executor] Cleaning up and closing token manager.")
            token_manager.close()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancels the agent task."""
        logging.warning(f"[agent_executor] Cancel requested for context ID: {context.context_id}")
        raise NotImplementedError('Cancel not yet supported.')