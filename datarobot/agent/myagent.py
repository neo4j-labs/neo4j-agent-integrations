"""
Neo4j Research Agent — built on DataRobot's official `af-component-agent`
template (`base` framework), registered into the NeMo Agent Toolkit (NAT)
runtime and served through DataRobot's `dragent` front end (see
`agent/register.py` and `workflow.yaml`).

This is the single supported agent implementation for this repo. It uses:
- datarobot_genai SDK (`BaseAgent`, AG-UI streaming events) for the agent shell
- LangGraph for the planner -> writer orchestration
- `neo4j_tools.py` for direct Neo4j Cypher tools (LangChain `@tool`s)
- `mcp_client.py` (this repo's own RFC 9728 OAuth-aware client) for optional
  external MCP tool loading, e.g. the hosted Neo4j Aura MCP server

Local dev: `task dev` (runs `nat dragent serve --config_file workflow.yaml`).
"""
from __future__ import annotations

import os
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import litellm
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.graph import END, START, MessagesState, StateGraph

try:
    from datarobot_genai.core.agents import make_system_prompt
    from datarobot_genai.langgraph.agent import datarobot_agent_class_from_langgraph
    _DR_GENAI_AVAILABLE = True
except ImportError:
    _DR_GENAI_AVAILABLE = False

try:
    from . import mcp_client
    from .neo4j_tools import get_all_tools as get_neo4j_tools
except ImportError:
    import mcp_client  # type: ignore[no-redef]
    from neo4j_tools import get_all_tools as get_neo4j_tools  # type: ignore[no-redef]

litellm.modify_params = True

# System prompt — focused on the Neo4j companies knowledge graph
_NEO4J_SYSTEM_PROMPT = make_system_prompt(
    "You are a Neo4j-powered industry research agent with access to a company knowledge graph.\n"
    "\n"
    "You can query the graph directly or use native MCP tools if provided by the DataRobot platform.\n"
    "\n"
    "When you need to query the graph:\n"
    "- Use the available Neo4j tools (run_cypher_query, search_companies, etc.)\n"
    "- If a native MCP Cypher tool is available, prefer it\n"
    "- Otherwise format your Cypher query in a JSON block:\n"
    '{{\n  "cypher": "YOUR_QUERY_HERE"\n}}\n'
    "\n"
    "Neo4j Companies DB schema:\n"
    "- (:Organization) — id, name, summary\n"
    "- (:Person) — name\n"
    "- (:IndustryCategory) — name\n"
    "- (:Article) — id, title, date, sentiment, summary, author\n"
    "- (:Chunk) — text, embedding\n"
    "- (:City), (:Country)\n"
    "Relationships: HAS_CATEGORY, HAS_CEO, HAS_BOARD_MEMBER, IN_CITY, IN_COUNTRY, MENTIONS, HAS_CHUNK\n"
    "\n"
    "Always ground answers in tool results. Produce concise Markdown with sections:\n"
    "Executive Summary · Company Profile · Recent Developments · Organizational Network"
) if _DR_GENAI_AVAILABLE else ""


prompt_template = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful Neo4j research agent with access to a company knowledge graph. "
            "Chat history is provided via {chat_history} (may be empty). "
            f"The current year is {datetime.now().year}.",
        ),
        ("user", "{topic}"),
    ]
)


async def _execute_with_tools(cypher: str, tools: list[BaseTool]) -> str:
    """Try MCP/LangChain tools first, then fall back to direct Neo4j connection."""
    # 1. Try a registered MCP/LangChain tool that can execute Cypher
    for t in tools:
        if any(k in t.name.lower() for k in ["cypher", "neo4j", "query", "read"]):
            try:
                param_name = list(t.args.keys())[0] if hasattr(t, "args") and t.args else "query"
                result = await t.ainvoke({param_name: cypher})
                return str(getattr(result, "content", result))
            except Exception as e:
                return f"Tool execution failed: {e}"

    # 2. Try the bundled neo4j_tools.run_cypher_query tool
    try:
        try:
            from .neo4j_tools import run_cypher_query
        except ImportError:
            from neo4j_tools import run_cypher_query  # type: ignore[no-redef]
        result = run_cypher_query.invoke({"cypher_query": cypher})
        return str(result)
    except Exception:
        pass

    # 3. Direct driver fallback (uses env vars)
    try:
        from neo4j import GraphDatabase
        uri = os.environ.get("NEO4J_URI", "neo4j+s://demo.neo4jlabs.com:7687")
        user = os.environ.get("NEO4J_USERNAME", "companies")
        password = os.environ.get("NEO4J_PASSWORD", "companies")
        database = os.environ.get("NEO4J_DATABASE", "companies")
        with GraphDatabase.driver(uri, auth=(user, password)) as driver:
            with driver.session(database=database) as session:
                records = [r.data() for r in session.run(cypher)]
                return str(records)
    except Exception as e:
        return f"All execution paths failed: {e}"


def graph_factory(
    llm: BaseChatModel, tools: list[BaseTool], verbose: bool = False
) -> "StateGraph[MessagesState]":
    """Build a LangGraph workflow: planner (queries Neo4j) → writer (formats output)."""

    neo4j_tools = get_neo4j_tools()
    all_tools = tools + neo4j_tools
    tools_by_name = {t.name: t for t in all_tools}

    # Planner: queries Neo4j and researches the topic
    planner_prompt = ChatPromptTemplate.from_messages([
        ("system", _NEO4J_SYSTEM_PROMPT),
        ("placeholder", "{messages}"),
    ])
    planner_chain = planner_prompt | llm.bind_tools(all_tools) if all_tools else planner_prompt | llm

    _MAX_TOOL_ROUNDS = 4

    async def planner_node(state: MessagesState) -> dict:
        from langchain_core.messages import ToolMessage

        messages = list(state["messages"])
        new_messages: list = []

        for _ in range(_MAX_TOOL_ROUNDS):
            response = await planner_chain.ainvoke({"messages": messages})
            messages.append(response)
            new_messages.append(response)

            # Native tool-calling path: bound tools were invoked by the LLM.
            tool_calls = getattr(response, "tool_calls", None)
            if tool_calls:
                for call in tool_calls:
                    tool_name = call.get("name") if isinstance(call, dict) else call.name
                    tool_args = call.get("args") if isinstance(call, dict) else call.args
                    call_id = call.get("id") if isinstance(call, dict) else call.id
                    tool_obj = tools_by_name.get(tool_name)
                    if tool_obj is None:
                        result_text = f"Unknown tool: {tool_name}"
                    else:
                        try:
                            result_text = str(await tool_obj.ainvoke(tool_args))
                        except Exception as e:
                            result_text = f"Tool '{tool_name}' failed: {e}"
                    tool_msg = ToolMessage(content=result_text, tool_call_id=call_id)
                    messages.append(tool_msg)
                    new_messages.append(tool_msg)
                continue  # let the planner see tool results and decide next step

            # Fallback path: no bound tools — look for a raw Cypher JSON/code block.
            text_content = getattr(response, "content", "") or ""
            cypher_match = re.search(r'"cypher"\s*:\s*"((?:[^"\\]|\\.)*)"', text_content)
            if not cypher_match:
                backticks = "`" * 3
                cypher_match = re.search(rf"{backticks}(?:cypher|sql)?\s*(.*?)\s*{backticks}", text_content, re.DOTALL)

            if cypher_match:
                raw = cypher_match.group(1)
                cypher = raw.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t').strip()
                print(f"\n[NEO4J AGENT] Executing Cypher:\n{cypher}\n", flush=True)
                db_result = await _execute_with_tools(cypher, tools)
                tool_msg = HumanMessage(
                    content=(
                        f"Cypher query executed successfully.\nResults:\n{db_result}\n\n"
                        "Use these results to plan your research outline."
                    )
                )
                messages.append(tool_msg)
                new_messages.append(tool_msg)
                continue

            # No tool calls and no Cypher block — the planner is done.
            break

        return {"messages": new_messages}

    # Writer: formats the planner's research into a clean report
    writer_prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            make_system_prompt(
                "You are a technical writer. Take the research outline from the planner and write "
                "a concise, publication-ready Markdown report under 500 words. "
                "Include sections: Executive Summary, Key Findings, and Recommendations."
            ) if _DR_GENAI_AVAILABLE else
            "You are a technical writer. Format the research results into a concise Markdown report under 500 words.",
        ),
        ("placeholder", "{messages}"),
    ])
    writer_chain = writer_prompt | llm

    async def writer_node(state: MessagesState) -> dict:
        response = await writer_chain.ainvoke({"messages": state["messages"]})
        return {"messages": [response]}

    def relay(state: MessagesState) -> dict:
        last = state["messages"][-1]
        return {"messages": [HumanMessage(content=last.content)]} if isinstance(last, AIMessage) else {"messages": []}

    graph = StateGraph(MessagesState)
    graph.add_node("planner_node", planner_node)
    graph.add_node("relay", relay)
    graph.add_node("writer_node", writer_node)
    graph.add_edge(START, "planner_node")
    graph.add_edge("planner_node", "relay")
    graph.add_edge("relay", "writer_node")
    graph.add_edge("writer_node", END)
    return graph


# DataRobot agent class — registered into NAT/dragent by agent/register.py.
# `LangGraphAgent.invoke(run_agent_input)` already yields the AG-UI event
# stream `register.py`'s `base_agent()` function expects, so no separate
# chat-completion adaptor is needed (that indirection was the DRUM-era
# `custom.py`/`agent.py` path, now retired).
if _DR_GENAI_AVAILABLE:
    MyAgent = datarobot_agent_class_from_langgraph(graph_factory, prompt_template)


_JSON_SCHEMA_TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _mcp_tool_args_schema(input_schema: dict[str, Any]) -> type | None:
    """Build a Pydantic args schema from an MCP tool's JSON Schema, if any."""
    properties = (input_schema or {}).get("properties") or {}
    if not properties:
        return None
    from pydantic import Field, create_model

    required = set((input_schema or {}).get("required") or [])
    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        py_type = _JSON_SCHEMA_TYPES.get(prop_schema.get("type", "string"), str)
        description = prop_schema.get("description", "")
        if prop_name in required:
            fields[prop_name] = (py_type, Field(description=description))
        else:
            fields[prop_name] = (py_type | None, Field(default=None, description=description))
    return create_model("MCPToolArgs", **fields)  # type: ignore[call-overload]


def _build_mcp_langchain_tool(tool_def: dict[str, Any]) -> BaseTool:
    """Wrap one MCP tool definition (name/description/inputSchema) as a LangChain tool."""
    name = tool_def["name"]
    description = tool_def.get("description") or f"MCP tool: {name}"

    async def _run(**kwargs: Any) -> str:
        result = await mcp_client.acall_tool(name, kwargs)
        return str(result)

    return StructuredTool.from_function(
        coroutine=_run,
        name=name,
        description=description,
        args_schema=_mcp_tool_args_schema(tool_def.get("inputSchema") or {}),
    )


@asynccontextmanager
async def mcp_tools_context(mcp_config: Any = None) -> AsyncGenerator[list[BaseTool], None]:
    """Load external MCP tools (e.g. the hosted Neo4j Aura MCP server) as LangChain tools.

    Uses this repo's own RFC 9728 OAuth-discovery-aware client
    (`agent/mcp_client.py`) rather than `datarobot_genai`'s built-in MCP
    adapter, since the latter expects auth headers already resolved by
    DataRobot's own MCP function-group machinery, while an external Neo4j
    Aura MCP endpoint needs its own OAuth client-credentials/discovery flow.
    Yields [] (never raises) if MCP isn't configured or fails to connect,
    matching the graceful-fallback behavior `mcp_client.py` already has.
    """
    if not mcp_client.is_enabled():
        yield []
        return
    try:
        tool_defs = await mcp_client.alist_tools()
        yield [_build_mcp_langchain_tool(t) for t in tool_defs]
    except Exception:
        yield []
