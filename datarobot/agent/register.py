"""NAT registration for the Neo4j research agent.

Wires `agent/myagent.py`'s LangGraph-based `MyAgent` into the NeMo Agent
Toolkit (NAT) runtime as a per-user function, following the exact pattern
DataRobot's official `af-component-agent` template (`base` framework)
generates via `register.py.jinja` / `register_templates/register_base.py.j2`.

This is what `workflow.yaml`'s `functions.neo4j_agent` entry (`_type:
neo4j_agent`) resolves to, and what makes the agent reachable through the
`dragent_fastapi` front end declared there.
"""
from collections.abc import AsyncGenerator
from typing import Annotated, Any

from ag_ui.core import RunAgentInput
from datarobot_genai.core.telemetry.agent import instrument
from datarobot_genai.dragent.frontends.response import DRAgentEventResponse
from datarobot_genai.langgraph.llm import get_llm
from nat.builder.builder import Builder
from nat.cli.register_workflow import register_per_user_function
from nat.data_models.agent import AgentBaseConfig
from nat.data_models.component_ref import FunctionGroupRef

# INSTRUMENTATION CALL IS REQUIRED TO SETUP TRACING AND TELEMETRY FOR AGENTS
instrument()

_PLACEHOLDER_MODELS = frozenset({"unknown"})


class Neo4jAgentConfig(AgentBaseConfig, name="neo4j_agent"):  # type: ignore[call-arg, misc]
    """NAT config for the Neo4j research agent.

    Extends AgentBaseConfig which provides: llm_name, description, verbose.
    """

    tool_names: list[FunctionGroupRef] = []


@register_per_user_function(  # type: ignore[untyped-decorator]
    config_type=Neo4jAgentConfig,
    input_type=RunAgentInput,
    streaming_output_type=DRAgentEventResponse,
)
async def neo4j_agent(
    config: Neo4jAgentConfig, builder: Builder
) -> AsyncGenerator[Any, None]:
    from datarobot_genai.core.mcp import MCPConfig
    from datarobot_genai.dragent.context import (
        extract_authorization_from_context,
        extract_datarobot_headers_from_context,
    )
    from datarobot_genai.dragent.frontends.converters import (
        aggregate_dragent_event_responses,
    )
    from nat.builder.function_info import FunctionInfo, Streaming

    from agent.myagent import MyAgent, mcp_tools_context

    async def _response_fn(
        input_message: RunAgentInput,
    ) -> Annotated[
        AsyncGenerator[DRAgentEventResponse, None],
        # Streaming tells NAT how to go from a list of streaming events to a single response
        # object for non-streaming routes.
        Streaming(convert=aggregate_dragent_event_responses),
    ]:
        # Agent should have access to request-specific headers and authorization context
        forwarded_headers = extract_datarobot_headers_from_context()
        authorization_context = extract_authorization_from_context()
        mcp_config = MCPConfig(
            forwarded_headers=forwarded_headers,
            authorization_context=authorization_context,
        )
        forwarded_props = getattr(input_message, "forwarded_props", None)
        model_name = (
            forwarded_props.get("model")
            if isinstance(forwarded_props, dict)
            else None
        )
        async with mcp_tools_context(mcp_config) as mcp_tools:
            agent = MyAgent(
                llm=get_llm(
                    model_name=model_name if model_name not in _PLACEHOLDER_MODELS else None
                ),
                verbose=config.verbose,
                forwarded_headers=forwarded_headers,
                tools=mcp_tools,
            )

            async for event, pipeline_interactions, usage_metrics in agent.invoke(
                input_message
            ):
                yield DRAgentEventResponse(
                    events=[event],
                    usage_metrics=usage_metrics,
                    pipeline_interactions=pipeline_interactions,
                )

    yield FunctionInfo.from_fn(
        _response_fn,
        description=config.description,
    )
