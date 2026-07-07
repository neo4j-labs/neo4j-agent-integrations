"""Neo4j Agent Memory (NAMS) — optional, non-blocking integration.

Uses the official neo4j-agent-memory Python SDK (>= 0.4.0).
For most production NAMS API keys the workspace is implicit in the key itself.
Some NAMS deployments (e.g. dev/staging services that scope by header rather
than encoding the workspace in the key) additionally require MEMORY_WORKSPACE_ID
to be set — the SDK's MemorySettings picks this up from the environment
automatically. If it's required but missing, NAMS calls fail with a
"workspace_not_provisioned" error, which is surfaced below as a one-time
warning (see _warn_once) rather than being silently swallowed.

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

_warned_this_process = False


def _warn_once(exc: BaseException) -> None:
    """Surface memory failures once per process instead of swallowing them.

    Memory is optional/non-blocking by design, but a silent failure here is
    just as confusing to operators as the MCP silent-disable bug fixed
    elsewhere in this agent — so we log a WARNING (visible by default, even
    without any logging configuration) the first time a call fails.
    """
    global _warned_this_process
    if _warned_this_process:
        logger.debug("Memory call failed (non-fatal, already warned): %s", exc)
        return
    _warned_this_process = True
    hint = ""
    if "workspace_not_provisioned" in str(exc):
        hint = (
            " This looks like the NAMS API key's workspace isn't provisioned, "
            "or this deployment requires MEMORY_WORKSPACE_ID to be set explicitly."
        )
    logger.warning(
        "Agent memory (NAMS) call failed; continuing without memory context.%s Error: %s",
        hint,
        exc,
    )


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
        pass  # not inside an anyio thread context — fall through to plain asyncio below

    # Fallback: plain asyncio (works when not inside an existing event loop)
    try:
        import asyncio
        return asyncio.run(_fetch())
    except Exception as exc:
        _warn_once(exc)
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
        _warn_once(exc)
