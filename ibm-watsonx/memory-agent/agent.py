"""LangGraph agent for watsonx Orchestrate: long-term memory + graph queries.

The agent combines two Neo4j-backed capabilities in one graph:

  * Long-term memory via the Neo4j Agent Memory Service (NAMS). Facts about
    people and their preferences are recalled at the start of every turn and
    persisted at the end, so they survive across sessions.
  * Company knowledge via direct Cypher queries against a Neo4j "companies"
    graph, exposed to the LLM as tools.

Routing is decided by the LLM. Memory is recalled every turn (cheap and
scoped), but the companies graph is queried only when the model chooses to
call a graph tool, so questions that need no graph data incur no graph query.

Turn flow (a single graph node running an internal loop):

    recall memory (NAMS) -> LLM (+ graph tools, looped) -> persist (NAMS)

The node returns exactly one plain assistant message to Orchestrate. Keeping
the tool-call / tool-result messages internal avoids passing message shapes
that the platform's response layer cannot serialise.

Credentials for NAMS and the LLM are injected by watsonx Orchestrate from
agent connections, keyed as ``{connection_app_id}_{credential_type}``. The
companies graph uses the public Neo4j demo database.
"""

import json
import urllib.error
import urllib.request
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables.config import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from neo4j import GraphDatabase

# --- NAMS (memory) -----------------------------------------------------------
NAMS_BASE_URL = "https://memory.neo4jlabs.com/v1"
REQUEST_TIMEOUT_SECONDS = 20
MAX_ENTITIES = 10
# NAMS /entities/search returns all entities ranked by vector similarity.
# Keep only reasonably relevant matches so unrelated facts do not leak in.
MIN_SCORE = 0.6

# --- Companies graph (public Neo4j demo database) ----------------------------
COMPANIES_URI = "neo4j+s://demo.neo4jlabs.com:7687"
COMPANIES_AUTH = ("companies", "companies")
COMPANIES_DATABASE = "companies"
MAX_ROWS = 20

# --- LLM ---------------------------------------------------------------------
LLM_MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = (
    "You are an assistant with two Neo4j-backed capabilities:\n"
    "1. Long-term memory about the user's preferences.\n"
    "2. A companies knowledge graph you can query with tools.\n\n"
    "Use the known facts to personalise answers. Call get_graph_schema when you "
    "need to understand the graph, and run_graph_query to answer questions about "
    "companies, people, or investments. Only query the graph when the question "
    "needs it. If the user states a key fact worth remembering, acknowledge it plainly.\n\n"
    "{context}"
)

NO_CONTEXT = "No facts recalled."


class AgentState(TypedDict):
    """Graph state exposed to Orchestrate: a single assistant message.

    The LLM/tool working history is kept inside the agent node and never
    returned, so only clean messages reach the platform response layer.
    """

    messages: Annotated[List[BaseMessage], add_messages]


def _credentials(config: RunnableConfig) -> Dict[str, Any]:
    return config.get("configurable", {}).get("credentials", {}) or {}


def _latest_user_message(state: AgentState) -> str:
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            return message.content
    return ""


def _nams_request(
    method: str,
    path: str,
    api_key: str,
    workspace_id: str,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Call the NAMS REST API and return the parsed JSON response."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{NAMS_BASE_URL}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-Workspace-Id": workspace_id,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def _format_entities(entities: List[Dict[str, Any]]) -> str:
    """Render relevant entities as a fact list for the prompt.

    Entities are filtered by similarity score, skipping empty-description
    matches, and formatted from the NAMS name, type, and description fields.
    """
    lines = []
    for entity in entities:
        if entity.get("score", 0) < MIN_SCORE:
            continue
        description = entity.get("description", "")
        if not description:
            continue
        name = entity.get("name", "")
        entity_type = entity.get("type", "")
        lines.append(f"- {name} ({entity_type}): {description}")
        if len(lines) >= MAX_ENTITIES:
            break
    if not lines:
        return NO_CONTEXT
    return "Known facts from long-term memory:\n" + "\n".join(lines)


# --- Companies graph tools ---------------------------------------------------

def _build_graph_tools() -> list:
    """Return LangChain tools that query the companies graph over Bolt."""

    @tool
    def get_graph_schema() -> str:
        """Return the companies graph schema: node labels, relationship types,
        and property keys. Call this before writing a Cypher query if the graph
        structure is unknown."""
        query = """
        CALL apoc.meta.data() YIELD label, other, elementType, type, property
        WITH label, elementType, collect(DISTINCT property) AS properties
        RETURN label, elementType, properties
        """
        try:
            with GraphDatabase.driver(COMPANIES_URI, auth=COMPANIES_AUTH) as driver:
                records, _, _ = driver.execute_query(query, database_=COMPANIES_DATABASE)
            return json.dumps([r.data() for r in records], indent=2)
        except Exception as exc:  # noqa: BLE001 - return a readable message to the LLM
            return f"Error reading schema: {exc}"

    @tool
    def run_graph_query(cypher: str) -> str:
        """Run a read-only Cypher query against the companies graph and return
        the rows as JSON. Use for questions about companies, people, industries,
        or investments. Always include a LIMIT of 20 or fewer."""
        if not cypher:
            return "No query provided."
        lowered = cypher.lower()
        if any(word in lowered for word in ("create", "merge", "delete", "set", "remove", "drop")):
            return "Only read-only queries are allowed."
        try:
            with GraphDatabase.driver(COMPANIES_URI, auth=COMPANIES_AUTH) as driver:
                records, _, _ = driver.execute_query(cypher, database_=COMPANIES_DATABASE)
            rows = [r.data() for r in records][:MAX_ROWS]
            return json.dumps(rows, indent=2) if rows else "No results."
        except Exception as exc:  # noqa: BLE001 - return a readable message to the LLM
            return f"Error running query: {exc}"

    return [get_graph_schema, run_graph_query]


def create_agent(config: RunnableConfig) -> StateGraph:
    """Factory returning an uncompiled StateGraph.

    watsonx Orchestrate compiles and runs the graph and injects connection
    credentials at runtime.
    """
    credentials = _credentials(config)
    llm_api_key = credentials.get("llm_openai_api_key")
    nams_api_key = credentials.get("nams_api_api_key")
    nams_workspace_id = credentials.get("nams_workspace_api_key")

    graph_tools = _build_graph_tools()
    tools_by_name = {t.name: t for t in graph_tools}

    def _recall_context(state: AgentState) -> str:
        try:
            response = _nams_request(
                "POST",
                "/entities/search",
                nams_api_key,
                nams_workspace_id,
                {"query": _latest_user_message(state), "limit": MAX_ENTITIES},
            )
            entities = (response or {}).get("entities", [])
            if entities:
                return _format_entities(entities)
        except Exception:  # noqa: BLE001 - recall is best-effort
            pass
        return NO_CONTEXT

    def _persist(text: str) -> None:
        if not (text and nams_api_key):
            return
        try:
            conversation = _nams_request(
                "POST", "/conversations", nams_api_key, nams_workspace_id, {}
            )
            conversation_id = (conversation or {}).get("id")
            if conversation_id:
                _nams_request(
                    "POST",
                    f"/conversations/{conversation_id}/messages",
                    nams_api_key,
                    nams_workspace_id,
                    {"role": "user", "content": text},
                )
        except Exception:  # noqa: BLE001 - storage is best-effort
            pass

    def agent(state: AgentState) -> AgentState:
        """Single node: recall memory, run an internal LLM+tools loop, persist,
        and return exactly one plain AIMessage to Orchestrate."""
        if not llm_api_key:
            return {"messages": [AIMessage(content="No LLM credentials were provided.")]}

        context = _recall_context(state)
        system_message = SystemMessage(content=SYSTEM_PROMPT.format(context=context))
        llm = ChatOpenAI(model=LLM_MODEL, api_key=llm_api_key).bind_tools(graph_tools)

        # Internal working history - never returned to Orchestrate directly.
        working: List[BaseMessage] = [system_message] + list(state["messages"])

        final_text = ""
        for _ in range(5):  # bounded tool loop
            reply = llm.invoke(working)
            working.append(reply)
            tool_calls = getattr(reply, "tool_calls", None) or []
            if not tool_calls:
                final_text = reply.content or ""
                break
            for call in tool_calls:
                tool = tools_by_name.get(call["name"])
                result = tool.invoke(call["args"]) if tool else f"Unknown tool {call['name']}"
                working.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        else:
            final_text = "I could not complete the request within the step limit."

        _persist(_latest_user_message(state))

        # Return ONE clean message: plain content, no tool_calls or metadata.
        return {"messages": [AIMessage(content=final_text)]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    graph.add_edge("agent", END)
    return graph
