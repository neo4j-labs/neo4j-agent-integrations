"""LangGraph agent for watsonx Orchestrate that queries Neo4j through MCP.

The agent talks to the neo4j-mcp-finance server on the AgentCore gateway. The
gateway exposes two tools, a schema reader and a read-only Cypher runner, and
the LLM decides when to call them.

Graph flow:

    prepare -> agent -> tools -> agent -> ... -> respond

``working`` holds the LLM and tool history for the turn. ``messages`` is what
Orchestrate sees, and only ``respond`` writes to it, with one plain AIMessage.
Keeping tool messages out of ``messages`` avoids shapes the platform's
response layer cannot serialise.

Orchestrate injects connection credentials into the factory config, keyed as
``{connection_app_id}_{credential_type}``:

    finance_llm_openai_api_key           OpenAI key
    neo4j_mcp_finance_access_token       Cognito access token, fetched by Orchestrate
    neo4j_mcp_finance_token_type         Token type, normally Bearer
    neo4j_mcp_finance_url                Gateway MCP URL set on the connection
"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables.config import RunnableConfig
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

LLM_MODEL = "gpt-5.6-terra"
MAX_TOOL_ROUNDS = 6

LLM_KEY = "finance_llm_openai_api_key"
TOKEN_KEY = "neo4j_mcp_finance_access_token"
TOKEN_TYPE_KEY = "neo4j_mcp_finance_token_type"
URL_KEY = "neo4j_mcp_finance_url"

SYSTEM_PROMPT = (
    "You answer questions about a banking graph in Neo4j. Call the schema tool "
    "first if you do not know the labels, relationship types, or properties. "
    "Then answer with the read-only Cypher tool. Always add a LIMIT of 25 or "
    "fewer. Base every answer on query results and say plainly when a query "
    "returns nothing."
)


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    working: Annotated[list[AnyMessage], add_messages]


def _credentials(config: RunnableConfig) -> dict[str, Any]:
    return config.get("configurable", {}).get("credentials", {}) or {}


def _latest_user_message(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) or getattr(message, "type", "") == "human":
            return str(message.content)
    return ""


def create_agent(config: RunnableConfig) -> StateGraph:
    """Factory returning an uncompiled StateGraph for Orchestrate to run."""
    credentials = _credentials(config)
    llm_key = credentials.get(LLM_KEY)
    token = credentials.get(TOKEN_KEY)
    token_type = credentials.get(TOKEN_TYPE_KEY) or "Bearer"
    gateway_url = credentials.get(URL_KEY)
    tools_cache: dict[str, Any] = {}

    async def load_tools() -> dict[str, Any]:
        """Connect to the gateway once per run and index the tools by name."""
        if not tools_cache:
            if not (token and gateway_url):
                raise ValueError(
                    f"No gateway credential. Keys present: {sorted(credentials)}"
                )
            client = MultiServerMCPClient(
                {
                    "finance": {
                        "transport": "streamable_http",
                        "url": gateway_url,
                        "headers": {"Authorization": f"{token_type} {token}"},
                    }
                }
            )
            tools_cache.update({t.name: t for t in await client.get_tools()})
        return tools_cache

    def prepare(state: AgentState) -> dict:
        question = _latest_user_message(state["messages"])
        return {
            "working": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=question),
            ]
        }

    async def agent(state: AgentState) -> dict:
        if not llm_key:
            raise ValueError(f"No LLM credential. Keys present: {sorted(credentials)}")
        tools = await load_tools()
        llm = ChatOpenAI(
            model=LLM_MODEL, api_key=llm_key, use_responses_api=True
        ).bind_tools(list(tools.values()))
        return {"working": [await llm.ainvoke(state["working"])]}

    async def run_tools(state: AgentState) -> dict:
        tools = await load_tools()
        results = []
        for call in state["working"][-1].tool_calls:
            tool = tools.get(call["name"])
            if tool is None:
                output = f"Unknown tool {call['name']}"
            else:
                try:
                    output = await tool.ainvoke(call["args"])
                except Exception as exc:  # noqa: BLE001 - give the LLM a readable error
                    output = f"Tool error: {exc}"
            results.append(ToolMessage(content=str(output), tool_call_id=call["id"]))
        return {"working": results}

    def route(state: AgentState) -> str:
        rounds = sum(isinstance(m, ToolMessage) for m in state["working"])
        has_calls = bool(getattr(state["working"][-1], "tool_calls", None))
        return "tools" if has_calls and rounds < MAX_TOOL_ROUNDS else "respond"

    def respond(state: AgentState) -> dict:
        last = state["working"][-1]
        text = str(last.text) if isinstance(last, AIMessage) else ""
        return {
            "messages": [
                AIMessage(content=text or "I could not finish within the step limit.")
            ]
        }

    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare)
    graph.add_node("agent", agent)
    graph.add_node("tools", run_tools)
    graph.add_node("respond", respond)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "agent")
    graph.add_conditional_edges(
        "agent", route, {"tools": "tools", "respond": "respond"}
    )
    graph.add_edge("tools", "agent")
    graph.add_edge("respond", END)
    return graph
