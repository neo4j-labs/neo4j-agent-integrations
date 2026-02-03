#!/usr/bin/env python3
"""
Multi-Agent Orchestrator for Neo4j MCP

A supervisor agent that routes queries to specialized workers:
- Maintenance Agent: reliability, faults, components, sensors
- Operations Agent: flights, delays, routes, airports

Uses LangGraph StateGraph for multi-agent orchestration.

Local testing:
    python orchestrator_agent.py
    curl -X POST http://localhost:8080/invocations \
        -H "Content-Type: application/json" \
        -d '{"prompt": "What are the most common maintenance faults?"}'

Cloud deployment:
    agentcore configure -e orchestrator_agent.py
    agentcore deploy
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, TypedDict, Annotated

import boto3
import httpx
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from maintenance_agent import MAINTENANCE_SYSTEM_PROMPT
from operations_agent import OPERATIONS_SYSTEM_PROMPT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Reduce noise from libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Create the AgentCore app
app = BedrockAgentCoreApp()

# Configuration
MODEL_ID = os.getenv("MODEL_ID", "us.anthropic.claude-sonnet-4-20250514-v1:0")
AWS_REGION = os.getenv("AWS_REGION", "us-west-2")

# In-memory caches
_CREDENTIALS: dict | None = None


# =============================================================================
# Credential Management
# =============================================================================

def load_credentials() -> dict:
    """Load credentials from in-memory cache."""
    global _CREDENTIALS

    if _CREDENTIALS is None:
        credentials_file = Path(__file__).parent / ".mcp-credentials.json"
        if not credentials_file.exists():
            raise FileNotFoundError(
                f"Credentials file not found: {credentials_file}\n"
                "Copy .mcp-credentials.json from basic-agent or MCP server deployment."
            )
        with open(credentials_file) as f:
            _CREDENTIALS = json.load(f)
        logger.info("Credentials loaded into memory")

    return _CREDENTIALS


def check_token_expiry(credentials: dict) -> bool:
    """Check if the token is expired. Returns True if valid."""
    expires_at_str = credentials.get("token_expires_at")
    if not expires_at_str:
        return False
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        now = datetime.now(timezone.utc)
        return now < (expires_at - timedelta(minutes=5))
    except (ValueError, TypeError):
        return False


def refresh_token(credentials: dict) -> dict:
    """Refresh the OAuth2 access token."""
    token_url = credentials.get("token_url")
    client_id = credentials.get("client_id")
    client_secret = credentials.get("client_secret")
    scope = credentials.get("scope")

    if not all([token_url, client_id, client_secret]):
        raise ValueError("Missing token refresh credentials")

    logger.info("Refreshing OAuth2 token...")
    response = httpx.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    token_data = response.json()

    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    credentials["access_token"] = token_data["access_token"]
    credentials["token_expires_at"] = expires_at.isoformat()

    logger.info(f"Token refreshed. Expires: {expires_at.isoformat()}")
    return credentials


# =============================================================================
# LLM and MCP Setup
# =============================================================================

def get_llm(region: str = AWS_REGION):
    """Get Claude LLM via AWS Bedrock Converse API."""
    bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    return ChatBedrockConverse(
        client=bedrock_client,
        model=MODEL_ID,
        temperature=0,
    )


async def get_mcp_tools(gateway_url: str, access_token: str) -> list:
    """Get MCP tools from the Neo4j server via Gateway."""
    mcp_client = MultiServerMCPClient(
        {
            "neo4j": {
                "transport": "streamable_http",
                "url": gateway_url,
                "headers": {
                    "Authorization": f"Bearer {access_token}",
                },
            }
        }
    )
    tools = await mcp_client.get_tools()
    logger.info(f"Loaded {len(tools)} MCP tools: {[t.name for t in tools]}")
    return tools


# =============================================================================
# Multi-Agent Orchestrator State
# =============================================================================

class OrchestratorState(TypedDict):
    """State for the orchestrator graph."""
    messages: Annotated[list[BaseMessage], add_messages]
    next_agent: str  # Which agent to route to


# =============================================================================
# Router Node - Classifies and routes queries
# =============================================================================

ROUTER_PROMPT = """You are a query router for an aviation fleet management system.

Analyze the user's question and determine which specialist should handle it.

MAINTENANCE keywords: maintenance, fault, failure, component, system, reliability, sensor, reading, repair, hydraulic, engine, avionics, critical, severity
OPERATIONS keywords: flight, delay, route, airport, operator, schedule, departure, arrival, on-time, airline, carrier

Respond with ONLY one word: either "maintenance" or "operations"

If the query is ambiguous or general (like "schema" or "count"), respond with "operations"."""


def create_router_node(llm):
    """Create the router node that classifies queries."""

    async def router(state: OrchestratorState) -> dict:
        """Route the query to the appropriate specialist."""
        logger.info("[Router] Classifying query...")

        # Get the user's question from messages
        user_message = None
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break

        if not user_message:
            return {"next_agent": "operations"}

        # Ask LLM to classify
        response = await llm.ainvoke([
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_message}
        ])

        classification = response.content.strip().lower()
        logger.info(f"[Router] Classification: {classification}")

        if "maintenance" in classification:
            return {"next_agent": "maintenance"}
        else:
            return {"next_agent": "operations"}

    return router


# =============================================================================
# Specialist Agents
# =============================================================================

def create_maintenance_node(llm, tools):
    """Create the maintenance specialist node."""
    agent = create_react_agent(llm, tools, prompt=MAINTENANCE_SYSTEM_PROMPT)

    async def maintenance_node(state: OrchestratorState) -> dict:
        logger.info("[Maintenance Agent] Processing query...")
        result = await agent.ainvoke({"messages": state["messages"]})
        logger.info("[Maintenance Agent] Done")
        return {"messages": result["messages"]}

    return maintenance_node


def create_operations_node(llm, tools):
    """Create the operations specialist node."""
    agent = create_react_agent(llm, tools, prompt=OPERATIONS_SYSTEM_PROMPT)

    async def operations_node(state: OrchestratorState) -> dict:
        logger.info("[Operations Agent] Processing query...")
        result = await agent.ainvoke({"messages": state["messages"]})
        logger.info("[Operations Agent] Done")
        return {"messages": result["messages"]}

    return operations_node


# =============================================================================
# Build the Orchestrator Graph
# =============================================================================

def route_to_agent(state: OrchestratorState) -> Literal["maintenance", "operations"]:
    """Conditional edge function to route to the correct agent."""
    return state["next_agent"]


async def create_orchestrator_graph(llm, tools):
    """Create the multi-agent orchestrator graph."""
    logger.info("Creating orchestrator graph...")

    # Build the graph
    graph = StateGraph(OrchestratorState)

    # Add nodes
    graph.add_node("router", create_router_node(llm))
    graph.add_node("maintenance", create_maintenance_node(llm, tools))
    graph.add_node("operations", create_operations_node(llm, tools))

    # Add edges
    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router",
        route_to_agent,
        {"maintenance": "maintenance", "operations": "operations"}
    )
    graph.add_edge("maintenance", END)
    graph.add_edge("operations", END)

    # Compile with memory
    memory = MemorySaver()
    compiled = graph.compile(checkpointer=memory)

    logger.info("Orchestrator graph created: Router -> [Maintenance | Operations]")
    return compiled


# =============================================================================
# AgentCore Entrypoint
# =============================================================================

def extract_prompt_from_payload(payload: dict) -> tuple[str | None, str, str]:
    """Extract prompt and context from payload."""
    prompt = (
        payload.get("prompt")
        or payload.get("message")
        or payload.get("query")
        or payload.get("inputText")
        or payload.get("input")
    )
    session_id = payload.get("session_id", "default_session")
    user_id = payload.get("user_id", "default_user")
    return prompt, session_id, user_id


@app.entrypoint
async def invoke(payload: dict = None):
    """
    AgentCore Runtime handler - Multi-Agent Orchestrator.

    Routes queries to Maintenance or Operations specialist agents.
    """
    logger.info(f"[Orchestrator] Received request: {list(payload.keys()) if payload else []}")

    if payload is None:
        payload = {}

    prompt, session_id, user_id = extract_prompt_from_payload(payload)

    if not prompt:
        logger.warning("No prompt provided")
        yield {"type": "error", "error": "No prompt provided. Include 'prompt' in request."}
        return

    logger.info(f"[Orchestrator] Query: {prompt[:100]}...")

    try:
        # Load credentials and refresh token if needed
        credentials = load_credentials()
        if not check_token_expiry(credentials):
            credentials = refresh_token(credentials)

        gateway_url = credentials["gateway_url"]
        access_token = credentials["access_token"]
        region = credentials.get("region", AWS_REGION)

        logger.info(f"[Orchestrator] Gateway: {gateway_url}")

        # Initialize LLM and get MCP tools
        llm = get_llm(region)
        tools = await get_mcp_tools(gateway_url, access_token)

        # Create the orchestrator graph
        graph = await create_orchestrator_graph(llm, tools)

        # Run the orchestrator with the user's query
        logger.info("[Orchestrator] Running multi-agent graph...")
        config = {"configurable": {"thread_id": session_id}}

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=prompt)], "next_agent": ""},
            config=config,
        )

        # Get the final response
        response_text = ""
        if result.get("messages"):
            last_msg = result["messages"][-1]
            if hasattr(last_msg, "content"):
                response_text = last_msg.content

        if not response_text:
            response_text = "No response from orchestrator"

        logger.info("[Orchestrator] Request completed successfully")

        yield {"type": "chunk", "data": response_text}
        yield {"type": "complete"}

    except FileNotFoundError as e:
        logger.error(f"Credentials error: {e}")
        yield {"type": "error", "error": str(e)}
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error: {e.response.status_code}")
        yield {"type": "error", "error": f"HTTP error {e.response.status_code}"}
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        yield {"type": "error", "error": f"Error: {str(e)}"}


if __name__ == "__main__":
    logger.info(f"Starting Multi-Agent Orchestrator with model: {MODEL_ID}")
    app.run()
