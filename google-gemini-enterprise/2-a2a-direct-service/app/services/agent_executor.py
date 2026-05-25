"""
Bridges the A2A protocol with the Google ADK LlmAgent, handling the core agent logic.
"""
import logging
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

from neo4j_agent_memory import MemoryClient, MemorySettings
from neo4j_agent_memory.config.settings import (
    EmbeddingConfig, 
    EmbeddingProvider, 
    Neo4jConfig,
    ExtractionConfig, 
    ExtractorType
)
from neo4j_agent_memory.integrations.google_adk import Neo4jMemoryService
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.load_memory_tool import LoadMemoryTool
from pydantic import SecretStr
from neo4j_agent_memory.config.settings import NamsConfig
from neo4j_agent_memory.embeddings.vertex_ai import VertexAIEmbedder

from ..core.config import (
    GEMINI_MODEL,
    TRACK_TOKEN_USAGE,
    current_user_identity,
    current_request_tokens,
    SERVICE_URL,
    AGENT_PROMPT,
    GCP_PROJECT_ID,  
    GCP_LOCATION
)
from .token_manager import TokenManager
from .custom_tools import get_tenant_tools
from neo4j import GraphDatabase

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
        user_email = current_user_identity.get()
        logging.info(f"[agent_executor] Executing task for user: {user_email} (Context ID provided: {bool(context.context_id)})")

        token_manager = TokenManager()
        memory_client = None
        neo4j_memory_service = None

        try:
            if TRACK_TOKEN_USAGE:
                logging.info("[agent_executor] Token usage tracking is enabled")
                if not token_manager.check_limit(user_email):
                    logging.warning(f"[agent_executor] User {user_email} has reached their daily token limit.")
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
                logging.warning(f"[agent_executor] User {user_email} exceeded query length limit ({len(user_query)} chars).")
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
                           
            logging.info(f"[agent_executor] Received query from user {user_email}: {user_query}")

            creds = token_manager.get_user_credentials(user_email)
            if not creds:
                logging.error(f"[agent_executor] Credentials not found or account inactive for {user_email}")
                onboarding_msg = (
                    f"Welcome! It looks like you haven't securely connected your Neo4j database yet.\n\n"
                    f"Please visit **{SERVICE_URL}/setup** to configure your credentials. "
                    f"Once you save them, come right back here and ask me a question!"
                )
                await event_queue.enqueue_event(new_agent_text_message(onboarding_msg))
                return

            dynamic_user = creds["user"]
            dynamic_pass = creds["password"]
            dynamic_uri = creds["uri"]
            dynamic_db = creds.get("database", "neo4j")

            logging.info("[agent_executor] Setting up main tenant tools")
            session_id = context.context_id
            if not session_id:
                session_id = f"session_{user_email}_{uuid.uuid4().hex}"
                logging.info(f"[agent_executor] Generated secure session ID for user {user_email}: {session_id}")

            session = await self.session_service.get_session(
                app_name="neo4j_a2a_app", user_id=user_email, session_id=session_id
            )

            if not session:
                session = await self.session_service.create_session(
                    session_id=session_id, state={}, app_name="neo4j_a2a_app", user_id=user_email
                )

            logging.info(f"[agent_executor] Running agent for session {session.id}")
            tenant_tools = get_tenant_tools(dynamic_user, dynamic_pass, dynamic_uri, dynamic_db)

            memory_uri = creds.get("memory_uri")
            memory_user = creds.get("memory_user")
            memory_password = creds.get("memory_password")
            memory_db = creds.get("memory_database", "neo4j")
            nams_api_key = creds.get("nams_api_key")

            using_nams = bool(nams_api_key)
            memory_enabled = using_nams or all([memory_uri, memory_user, memory_password])

            if memory_enabled:
                if using_nams:
                    logging.info(f"[agent_executor] NAMS API key present. Initializing Native NAMS backend.")
                    memory_settings = MemorySettings(
                        backend="nams",
                        nams=NamsConfig(
                            api_key=SecretStr(nams_api_key),
                            validate_on_connect=False 
                        )
                    )
                else:
                    logging.info(f"[agent_executor] Self-hosted memory configured. Initializing Bolt backend.")
                    memory_settings = MemorySettings(
                        backend="bolt",
                        neo4j=Neo4jConfig(
                            uri=memory_uri,
                            username=memory_user,
                            password=memory_password,
                            database=memory_db
                        ),
                        embedding="vertex_ai/text-embedding-004",
                        llm=f"vertex_ai/{GEMINI_MODEL}",
                        extraction=ExtractionConfig(extractor_type=ExtractorType.LLM)
                    )

                memory_client = MemoryClient(memory_settings)
                await memory_client.connect()

                neo4j_memory_service = Neo4jMemoryService(
                    memory_client=memory_client,
                    user_id=user_email,
                    include_entities=True,
                    include_preferences=True
                )
                
                if using_nams:
                    async def load_memory(query: str) -> str:
                        """Search past memories, preferences, and facts for the user."""
                        results_list = []
                        try:
                            logging.info(f"[agent_executor] LLM invoked short term load_memory with query: '{query}'")
                            response_msgs = await memory_client.short_term.search_messages(query, session_id=session.id, limit=3)
                            if response_msgs:
                                results_list.extend([f"- Chat: {m.content}" for m in response_msgs if getattr(m, 'content', None)])
                        except Exception as e:
                            logging.warning(f"[agent_executor] NAMS message search warning: {e}")

                        try:
                            logging.info(f"[agent_executor] LLM invoked long term load_memory with query: '{query}' for user {user_email}")
                            response_entities = await memory_client.long_term.search_entities(query=query, user_identifier=user_email, limit=3)
                            if response_entities:
                                for ent in response_entities:
                                    results_list.append(f"- Fact ({getattr(ent, 'name', 'Unknown')}): {getattr(ent, 'description', '')}")
                        except Exception as e:
                            logging.warning(f"[agent_executor] NAMS entity search warning: {e}")

                        return "\n".join(results_list) if results_list else "No memory found."

                    async def save_memory(fact: str, entity_name: str, entity_type: str) -> str:
                        """Saves an important user fact, preference, or memory instantly to the graph database.
                        Args:
                            fact: The detailed fact to remember (e.g., 'User's favorite coding language is Python').
                            entity_name: The core subject of the fact (e.g., 'Python').
                            entity_type: The category label (e.g., 'TECHNOLOGY', 'PREFERENCE', 'PERSON').
                        """
                        try:
                            await memory_client.long_term.add_entity(
                                name=entity_name,
                                entity_type=entity_type,
                                description=fact,
                                user_identifier=user_email
                            )
                            logging.info(f"[agent_executor] Synchronously wrote entity '{entity_name}' to NAMS.")
                            return f"Successfully saved '{entity_name}' to memory."
                        except Exception as e:
                            logging.error(f"[agent_executor] NAMS save failed: {e}")
                            return "Failed to save memory."

                    tenant_tools.extend([load_memory, save_memory])
                else:
                    tenant_tools.append(PreloadMemoryTool())
                    tenant_tools.append(LoadMemoryTool())

                if using_nams:
                    active_note = (
                        "\n\n[SYSTEM NOTE]: You are connected to a managed cloud graph database (NAMS). "
                        "If a user asks you to save, remember, or note something, you MUST use the `save_memory` tool to instantly write it to the database. "
                        "If a user asks you to retrieve, recall, or remind them of past information, you MUST use the `load_memory` tool."
                    )
                else:
                    active_note = (
                        "\n\n[SYSTEM NOTE]: You are connected to a self-hosted persistent memory database. "
                        "Your memory architecture is completely passive and automatic. Every conversation you have is automatically saved to the database in the background. "
                        "If a user asks you to save, remember, or note something, simply acknowledge their request in plain text (e.g., 'I will remember that.'). "
                        "You do NOT need a tool to save information. "
                        "If a user asks you to retrieve, recall, or remind them of past information, you MUST use the provided memory tools to search the database."
                    )

                active_instruction = AGENT_PROMPT + active_note
            else:
                logging.info(f"[agent_executor] Memory feature not configured for {user_email}. Proceeding stateless.")
                active_instruction = AGENT_PROMPT

            enterprise_safety_settings = [
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
                types.SafetySetting(
                    category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
                ),
            ]
            
            logging.info("[agent_executor] Instantiating ADK Agent")
            adk_agent = LlmAgent(
                model=GEMINI_MODEL,
                name="assistant",
                instruction=active_instruction,
                tools=tenant_tools,
                generate_content_config=types.GenerateContentConfig(
                    safety_settings=enterprise_safety_settings
                ),
                planner=BuiltInPlanner(
                    thinking_config=types.ThinkingConfig(
                        include_thoughts=False, 
                        thinking_budget=1024,
                    )
                ),
                after_model_callback=[track_token_usage_callback]
            )
            
            runner_kwargs = {
                "app_name": "neo4j_a2a_app",
                "agent": adk_agent,
                "artifact_service": self.artifact_service,
                "session_service": self.session_service,
            }
            if memory_enabled and not using_nams:
                runner_kwargs["memory_service"] = neo4j_memory_service
                
            runner = Runner(**runner_kwargs)

            total_response_text = ""
            content = types.Content(role='user', parts=[types.Part(text=user_query)])
            events_async = runner.run_async(session_id=session.id, user_id=user_email, new_message=content)

            async for event in events_async:
                if hasattr(event, 'content') and event.content:
                    for part in event.content.parts:
                        logging.info(f"[agent_executor] Processing new part from agent event: {part}")
                        if getattr(part, 'function_call', None) or getattr(part, 'function_response', None):
                            continue
                        elif getattr(part, 'text', None):
                            logging.info(f"[agent_executor] Received new text part from agent: {part.text}")
                            total_response_text += part.text
                            await event_queue.enqueue_event(new_agent_text_message(part.text))

            logging.info(f"[agent_executor] Agent execution finished. Total response length: {len(total_response_text)}")

            if memory_enabled:
                logging.info(f"[agent_executor] Syncing transaction context to memory for session {session.id}")
                try:
                    if using_nams:
                        await memory_client.short_term.create_conversation(
                            session_id=session.id, 
                            user_identifier=user_email
                        )

                        await memory_client.short_term.add_message(
                            session_id=session.id,
                            role="user",
                            content=user_query
                        )

                        if total_response_text:
                            await memory_client.short_term.add_message(
                                session_id=session.id,
                                role="assistant",
                                content=total_response_text
                            )
                        logging.info("[agent_executor] Native NAMS memory sync successful.")
                    else:
                        fresh_session = await self.session_service.get_session(
                            session_id=session.id, app_name="neo4j_a2a_app", user_id=user_email
                        )
                        if neo4j_memory_service:
                            await neo4j_memory_service.add_session_to_memory(fresh_session)
                        logging.info("[agent_executor] Bolt local memory sync successful.")
                except Exception as e:
                    logging.error(f"[agent_executor] Memory sync failed: {e}")

            if TRACK_TOKEN_USAGE:
                exact_tokens = current_request_tokens.get()
                if exact_tokens == 0:
                    exact_tokens = math.ceil((len(user_query) + len(total_response_text)) / 4)
                token_manager.add_tokens(user_email, exact_tokens)
                logging.info(f"[agent_executor] User {user_email} used {exact_tokens} tokens.")

        except Exception as e:
            error_message = str(e).lower()
            if "safety" in error_message or "blocked" in error_message:
                logging.warning(f"[agent_executor] Request blocked by Vertex AI Safety filters: {e}")
                await event_queue.enqueue_event(
                    new_agent_text_message("I cannot fulfill this request as it violates enterprise safety and content guidelines.")
                )
            else:
                logging.error(f"[agent_executor] ADK Execution Error: {e}", exc_info=True)
                await event_queue.enqueue_event(
                    new_agent_text_message("An unexpected error occurred while processing your request.")
                )
        finally:
            logging.info(f"[agent_executor] Cleaning up resources")
            logging.info(f"[agent_executor] Cleaning up resources")
            token_manager.close()
            if memory_client:
                try:
                    await memory_client.close()
                except Exception as e:
                    logging.warning(f"[agent_executor] Error closing memory client: {e}")
            try:
                if neo4j_memory_service and hasattr(neo4j_memory_service, 'close'):
                    await neo4j_memory_service.close()
            except Exception as e:
                logging.warning(f"[agent_executor] Error closing memory service client: {e}")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Cancels the agent task."""
        logging.warning(f"[agent_executor] Cancel requested for context ID: {context.context_id}")
        raise NotImplementedError('Cancel not yet supported.')