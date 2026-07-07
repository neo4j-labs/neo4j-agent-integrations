"""Neo4j Agent Memory (NAMS) — optional, non-blocking integration.

Uses the official neo4j-agent-memory Python SDK (>= 0.4.0).
Some NAMS deployments require MEMORY_WORKSPACE_ID in addition to
MEMORY_API_KEY (see the "workspace_not_provisioned" note below) — the
SDK's MemorySettings picks this up from the environment automatically.
If it's required but missing, NAMS calls fail with a
"workspace_not_provisioned" error, which is surfaced below as a one-time
warning (see _warn_once) rather than being silently swallowed.

IMPORTANT — NAMS conversation IDs are server-assigned, not client-chosen:
`POST /conversations` ignores any id we pass and always mints a fresh UUID
(the SDK's `create_conversation(session_id=...)` only echoes our value back
into the *local* `Conversation.session_id` field for Pydantic compatibility
— it is never sent to, or honored by, the server). Passing our own
locally-derived id (see `session_id_from_params`) straight through to
`add_message`/`get_context` therefore targets a conversation that was never
actually created, failing every call with a 404. Filtering
`list_conversations` by `user_identifier` was verified during end-to-end
testing to not reliably scope results server-side either, so it can't be
used to look up "our" conversation among others without risking
cross-session context leakage. Instead, `_resolve_conversation_id` keeps a
small local JSON cache mapping our local key -> the real NAMS conversation
UUID, created once via `create_conversation` and reused on every later
call. This gives stable per-key continuity for a single process/replica;
in a multi-replica deployment each replica keeps its own cache, so memory
continuity is scoped per-replica — a documented limitation, not a
correctness bug.

If neo4j-agent-memory is not installed or MEMORY_API_KEY is absent,
all functions are silent no-ops so the agent works normally.
"""
from __future__ import annotations
import hashlib, json, logging, os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    from neo4j_agent_memory import MemoryClient  # type: ignore[import]
    import anyio as _anyio  # type: ignore[import]
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

_warned_this_process = False

_CONVERSATION_CACHE_PATH = Path(__file__).resolve().parents[1] / ".nams_conversation_cache.json"


def _load_conversation_cache() -> dict[str, str]:
    try:
        return json.loads(_CONVERSATION_CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_conversation_cache(cache: dict[str, str]) -> None:
    try:
        _CONVERSATION_CACHE_PATH.write_text(json.dumps(cache))
    except Exception as exc:
        logger.debug("Could not persist NAMS conversation cache (non-fatal): %s", exc)


async def _resolve_conversation_id(client: Any, local_key: str) -> str:
    """Map our local session key to a real NAMS conversation UUID, creating one if needed."""
    cache = _load_conversation_cache()
    real_id = cache.get(local_key)
    if real_id:
        return real_id

    conv = await client.short_term.create_conversation(local_key, user_identifier=local_key)
    real_id = str(conv.id)
    cache[local_key] = real_id
    _save_conversation_cache(cache)
    return real_id


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
            real_id = await _resolve_conversation_id(client, conversation_id)
            ctx = await client.get_context(user_query, session_id=real_id)
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
            real_id = await _resolve_conversation_id(client, conversation_id)
            # NAMS SDK: add_message(conversation_id, role, content)
            await client.short_term.add_message(real_id, "user", user_message)
            await client.short_term.add_message(real_id, "assistant", assistant_response)

    try:
        import asyncio
        asyncio.run(_save())
    except Exception as exc:
        _warn_once(exc)
