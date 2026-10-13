"""The Phase 3 support agent: LangGraph's prebuilt ReAct agent over the tools.

``run_agent`` is the entry point shared by ``chat`` and ``eval-local``.
"""

import functools
import inspect
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from string import Template
from typing import Any, TypedDict

import neo4j
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from graphrag_banking import tools
from graphrag_banking.config import PROMPTS_DIR, Settings, get_driver, load_settings

INSTRUCTIONS_PATH = PROMPTS_DIR / "agent_instructions.md"

TOOLS = [
    tools.search_policies,
    tools.get_my_accounts,
    tools.find_my_transactions,
    tools.explain_transaction,
    tools.get_my_household,
    tools.get_scheduled_payments,
]


class ToolCall(TypedDict):
    """One tool call made while answering, in call order."""

    name: str
    args: dict[str, Any]
    # The tool's return value. Retrieved chunks appear here.
    result: Any
    # Every Cypher statement the tool ran.
    cypher: list[str]


class AgentResult(TypedDict):
    answer: str
    tool_calls: list[ToolCall]


def load_instructions(as_of: date) -> str:
    """Read the agent instructions and fill in the demo date."""
    template = Template(INSTRUCTIONS_PATH.read_text(encoding="utf-8"))
    return template.substitute(
        demo_as_of=as_of.isoformat(),
        demo_as_of_long=f"{as_of:%A, %B} {as_of.day}, {as_of.year}",
    )


def _bind(
    func: Callable[..., dict[str, Any]],
    context: tools.ToolContext,
    record: Callable[[ToolCall], None],
) -> StructuredTool:
    """Wrap a tool so the model sees only its own arguments.

    The context is passed in here, so the model never supplies a customer ID.
    Each call gets its own Cypher log, and is recorded for the trace.
    """

    @functools.wraps(func)
    def bound(**kwargs: Any) -> dict[str, Any]:
        call_context = replace(context, executed=[])
        try:
            result = func(call_context, **kwargs)
        except ValueError as error:
            # Bad arguments from the model. Tell it, so it can retry.
            result = {"error": str(error)}
        record(
            ToolCall(
                name=func.__name__,
                args=kwargs,
                result=result,
                cypher=call_context.executed,
            )
        )
        return result

    signature = inspect.signature(func)
    parameters = list(signature.parameters.values())[1:]
    bound.__signature__ = signature.replace(parameters=parameters)
    return StructuredTool.from_function(bound, parse_docstring=True)


class SupportAgent:
    """A conversation with the support agent, scoped to the demo customer.

    Args:
        settings: Model, customer, and date settings.
        driver: Open Neo4j driver. The caller owns and closes it.
    """

    def __init__(self, settings: Settings, driver: neo4j.Driver) -> None:
        context = tools.ToolContext(
            driver=driver,
            database=settings.neo4j_database,
            customer_id=settings.demo_customer_id,
            embedding_config=settings.embedding_config,
            as_of=settings.demo_as_of,
        )
        self._calls: list[ToolCall] = []
        self._messages: list[BaseMessage] = []
        model = ChatOpenAI(
            model=settings.chat_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        self._graph = create_react_agent(
            model,
            tools=[_bind(func, context, self._record) for func in TOOLS],
            prompt=load_instructions(settings.demo_as_of),
        )

    def _record(self, call: ToolCall) -> None:
        self._calls.append(call)

    def ask(self, prompt: str) -> AgentResult:
        """Send one message and return the answer with this turn's tool calls."""
        self._calls = []
        state = self._graph.invoke(
            {"messages": [*self._messages, HumanMessage(prompt)]}
        )
        self._messages = state["messages"]
        return AgentResult(answer=self._messages[-1].text, tool_calls=self._calls)


def run_agent(prompt: str, settings: Settings | None = None) -> AgentResult:
    """Answer one prompt in a fresh conversation.

    Args:
        prompt: The customer's message.
        settings: Settings to use. Loaded from the environment when ``None``.

    Returns:
        The final answer and the tool calls behind it.
    """
    settings = settings or load_settings()
    with get_driver(settings) as driver:
        return SupportAgent(settings, driver).ask(prompt)
