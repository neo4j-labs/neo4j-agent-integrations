from __future__ import annotations

import time
import uuid
from typing import Any


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def extract_user_prompt(completion_create_params: dict[str, Any]) -> str:
    messages = completion_create_params.get("messages", [])
    for message in reversed(messages):
        if message.get("role") == "user":
            prompt = _extract_text(message.get("content"))
            if prompt:
                return prompt
    raise ValueError("No user prompt found in completion_create_params['messages'].")


def build_agent_messages(
    system_prompt: str,
    completion_create_params: dict[str, Any],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for message in completion_create_params.get("messages", []):
        role = message.get("role")
        if role not in {"user", "assistant", "system"}:
            continue
        content = _extract_text(message.get("content"))
        if not content:
            continue
        if role == "system":
            role = "user"
            content = f"Additional caller instructions:\n{content}"
        messages.append({"role": role, "content": content})
    return messages


def empty_usage() -> dict[str, int]:
    return {
        "completion_tokens": 0,
        "prompt_tokens": 0,
        "total_tokens": 0,
    }


def merge_usage(current: dict[str, int], delta: Any) -> dict[str, int]:
    if delta is None:
        return current
    current["completion_tokens"] += int(getattr(delta, "completion_tokens", 0) or 0)
    current["prompt_tokens"] += int(getattr(delta, "prompt_tokens", 0) or 0)
    current["total_tokens"] += int(getattr(delta, "total_tokens", 0) or 0)
    return current


def to_custom_model_response(
    agent_result: str,
    usage_metrics: dict[str, int],
    model: str,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": agent_result,
                },
            }
        ],
        "usage": usage_metrics,
    }
