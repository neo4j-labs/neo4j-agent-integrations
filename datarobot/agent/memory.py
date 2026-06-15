"""Neo4j Agent Memory (NAMS) — optional, non-blocking integration.

If neo4j-agent-memory is not installed or MEMORY_API_KEY is absent,
all functions are silent no-ops so the agent works normally without memory.
"""
from __future__ import annotations
import asyncio, hashlib, logging, os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from neo4j_agent_memory import MemoryClient  # type: ignore[import]
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False


def is_enabled() -> bool:
    return _HAS_MEMORY and bool(os.environ.get("MEMORY_API_KEY"))


def session_id_from_params(params: dict[str, Any]) -> str:
    user = params.get("user")
    if user:
        return str(user)
    for msg in (params.get("messages") or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            digest = hashlib.sha256(str(msg.get("content") or "").encode()).hexdigest()[:16]
            return f"dr-session-{digest}"
    return "session-default"


def get_context(user_query: str, session_id: str) -> str:
    if not is_enabled():
        return ""
    async def _fetch() -> str:
        async with MemoryClient() as client:
            ctx = await client.get_context(user_query, session_id=session_id)
            return ctx or ""
    try:
        return asyncio.run(_fetch())
    except Exception as exc:
        logger.debug("Memory get_context failed (non-fatal): %s", exc)
        return ""


def save_turn(session_id: str, user_message: str, assistant_response: str) -> None:
    if not is_enabled():
        return
    async def _save() -> None:
        async with MemoryClient() as client:
            await client.short_term.add_message(session_id=session_id, role="user", content=user_message)
            await client.short_term.add_message(session_id=session_id, role="assistant", content=assistant_response)
    try:
        asyncio.run(_save())
    except Exception as exc:
        logger.debug("Memory save_turn failed (non-fatal): %s", exc)
