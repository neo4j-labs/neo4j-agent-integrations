import os
import uuid

from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from dotenv import load_dotenv
from strands import Agent, tool, ToolContext

from mcp_client.client import get_streamable_http_mcp_client
from model.load import load_model

load_dotenv()

app = BedrockAgentCoreApp()

log = app.logger

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MEMORY_ID = os.getenv("BEDROCK_AGENTCORE_MEMORY_ID")

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
Use the MCP tools to answer the questions.
Always use read-schema first to evaluate the graph schema if you want to execute any cypher queries.
Use all you know about the user to provide helpful responses.
"""


@tool(context=True)
def clear_preferences(tool_context: ToolContext):
    """Clear all stored user preferences for the current user."""
    actor_id = tool_context.invocation_state.get("actor_id")
    if not actor_id:
        return "No preferences found"

    client = MemoryClient()
    namespace = f"/users/{actor_id}/preferences/"

    response = client.list_memory_records(memoryId=MEMORY_ID, namespace=namespace)
    records = response.get("memoryRecordSummaries", [])

    if not records:
        return "No preferences found"

    deleted = 0
    for record in records:
        record_id = record.get("memoryRecordId") or record.get("id")
        try:
            client.delete_memory_record(
                memoryId=MEMORY_ID,
                memoryRecordId=record_id,
            )
            deleted += 1
        except Exception as e:
            log.error("Failed to delete record %s: %s", record_id, e)

    return f"Cleared {deleted} preference(s). The agent will no longer use prior preferences for your queries."


# ---------------------------------------------------------------------------
# Entrypoint — single-turn invocation
# ---------------------------------------------------------------------------

@app.entrypoint
async def invoke(payload, context):
    # ── Resolve session ID from the AgentCore request context ────────────
    session_id = context.session_id if context and context.session_id else f"{uuid.uuid4()}"
    actor_id = payload.get("actor_id")
    if not actor_id:
        raise ValueError("actor_id is required in the payload")

    tools = []

    # Configure memory if available
    session_manager = None
    if MEMORY_ID:
        session_manager = AgentCoreMemorySessionManager(
            AgentCoreMemoryConfig(
                memory_id=MEMORY_ID,
                session_id=session_id,
                actor_id=actor_id,
                retrieval_config={
                    f"/users/{actor_id}/preferences/": RetrievalConfig(top_k=5, relevance_score=0.5),
                }
            ),
        )
        tools.append(clear_preferences)
    else:
        log.warning("MEMORY_ID is not set. Skipping memory session manager initialization.")

    # ── Neo4j MCP client ─────────────────────────────────────────────────
    neo4j_mcp_client = get_streamable_http_mcp_client()
    tools.append(neo4j_mcp_client)

    # ── Run single turn ──────────────────────────────────────────────────
    agent = Agent(
        model=load_model(),
        session_manager=session_manager,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
    )

    user_message = payload.get(
        "prompt", "No prompt found in input, please guide customer to create a json payload with prompt key"
    )
    stream = agent.stream_async(user_message, actor_id=actor_id)

    async for event in stream:
        # Handle Text parts of the response
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]


if __name__ == "__main__":
    app.run()
