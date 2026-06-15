"""Neo4j Agent Memory (NAMS) — optional, non-blocking integration.

Uses the official neo4j-agent-memory Python SDK (>= 0.4.0).
NAMS workspace is implicit in the MEMORY_API_KEY — no separate workspace_id needed.

If neo4j-agent-memory is not installed or MEMORY_API_KEY is absent,
all functions are silent no-ops so the agent works normally.
"""
from __future__ import annotations
import hashlib, logging, os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from neo4j_agent_memory import MemoryClient  # type: ignore[import]
    import anyio as _anyio  # type: ignore[import]
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False


def is_enabled() -> bool:
    return _HAS_MEMORY and bool(os.environ.get("MEMORY_API_KEY"))


def session_id_from_params(params: dict[str, Any]) -> str:
    """Derive a stable conversation ID from the OpenAI-style request."""
    user = params.get("user")
    if user:
        return str(user)
    for msg in (params.get("messages") or []):
        if isinstance(msg, dict) and msg.get("role") == "user":
            digest = hashlib.sha256(str(msg.get("content") or "").encode()).hexdigest()[:16]
            return f"dr-session-{digest}"
    return "session-default"


def get_context(user_query: str, conversation_id: str) -> str:
    """Fetch relevant past context from NAMS. Returns '' on any error or if disabled."""
    if not is_enabled():
        return ""

    async def _fetch() -> str:
        async with MemoryClient() as client:
            # Ensure conversation exists (idempotent on NAMS)
            try:
                await client.short_term.create_conversation(conversation_id)
            except Exception:
                pass  # already exists
            ctx = await client.get_context(user_query, session_id=conversation_id)
            return ctx or ""

    try:
        return _anyio.from_thread.run_sync(lambda: _anyio.run(_fetch))  # type: ignore[attr-defined]
    except Exception:
        pass

    # Fallback: plain asyncio (works when not inside an existing event loop)
    try:
        import asyncio
        return asyncio.run(_fetch())
    except Exception as exc:
        logger.debug("Memory get_context failed (non-fatal): %s", exc)
        return ""


def save_turn(conversation_id: str, user_message: str, assistant_response: str) -> None:
    """Persist a turn to NAMS short-term memory. Silent no-op on any error."""
    if not is_enabled():
        return

    async def _save() -> None:
        async with MemoryClient() as client:
            try:
                await client.short_term.create_conversation(conversation_id)
            except Exception:
                pass
            # NAMS SDK: add_message(conversation_id, role, content)
            await client.short_term.add_message(conversation_id, "user", user_message)
            await client.short_term.add_message(conversation_id, "assistant", assistant_response)

    try:
        import asyncio
        asyncio.run(_save())
    except Exception as exc:
        logger.debug("Memory save_turn failed (non-fatal): %s", exc)
