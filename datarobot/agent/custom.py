from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: object, **_kwargs: object) -> bool:  # type: ignore[misc]
        return False

try:
    from datarobot_drum import RuntimeParameters
except ImportError:
    class RuntimeParameters:  # type: ignore[override]
        @staticmethod
        def get(key: str) -> str:
            raise ValueError(f"Runtime parameter '{key}' is unavailable in local mode.")

try:
    from .agent import Neo4jResearchAgent
    from .helpers import to_custom_model_response
    from . import memory as mem
except ImportError:
    from agent import Neo4jResearchAgent  # type: ignore[no-redef]
    from helpers import to_custom_model_response  # type: ignore[no-redef]
    import memory as mem  # type: ignore[no-redef]

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

RUNTIME_PARAMETER_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "AGENT_MAX_TOOL_STEPS",
    "MEMORY_API_KEY",
    "MEMORY_WORKSPACE_ID",
    "MCP_SERVER_URL",
)


def _coerce_runtime_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("apiToken", "token", "value"):
            if key in value and value[key]:
                return str(value[key])
        return json.dumps(value)
    return str(value)


def maybe_set_env_from_runtime_parameters(key: str) -> None:
    placeholder = "SET_VIA_PULUMI_OR_MANUALLY"
    try:
        runtime_parameter_value = RuntimeParameters.get(key)
    except ValueError:
        return
    if not runtime_parameter_value:
        return
    value = _coerce_runtime_value(runtime_parameter_value)
    if value and value != placeholder:
        os.environ[key] = value


def load_model(code_dir: str) -> str:
    _ = code_dir
    for key in RUNTIME_PARAMETER_KEYS:
        maybe_set_env_from_runtime_parameters(key)
    return "ready"


def chat(
    completion_create_params: dict[str, Any],
    model: str | None = None,
) -> dict[str, Any]:
    for key in RUNTIME_PARAMETER_KEYS:
        maybe_set_env_from_runtime_parameters(key)

    selected_model = completion_create_params.get("model") or os.environ.get(
        "OPENAI_MODEL", "gpt-4o-mini",
    )

    # --- agent-memory: derive session id + retrieve past context ---
    session_id = mem.session_id_from_params(completion_create_params)
    user_message = next(
        (m.get("content", "") for m in reversed(completion_create_params.get("messages", []))
         if isinstance(m, dict) and m.get("role") == "user"),
        "",
    )
    memory_context = mem.get_context(user_message, session_id)

    if memory_context:
        params_with_memory: dict[str, Any] = dict(completion_create_params)
        params_with_memory["messages"] = [
            {"role": "system", "content": f"[Relevant context from prior sessions]\n{memory_context}"},
            *completion_create_params.get("messages", []),
        ]
    else:
        params_with_memory = completion_create_params

    agent = Neo4jResearchAgent(model=selected_model)
    try:
        result, usage = agent.run(params_with_memory)
    finally:
        agent.close()

    # --- agent-memory: persist this turn for future sessions ---
    mem.save_turn(session_id, user_message, result)

    return to_custom_model_response(result, usage, selected_model)
