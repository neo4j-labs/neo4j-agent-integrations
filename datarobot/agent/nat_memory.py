"""NeMo Agent Toolkit (NAT) memory plugin backed by Neo4j Agent Memory (NAMS).

This is the `dr_mem0_memory`-equivalent plugin DataRobot's review asked for
(PR #67, jpclemens0): a NAT `MemoryEditor` implementation that can be
referenced from a `workflow.yaml`'s `memory:` section (e.g. by
`streaming_memory_agent`) exactly like DataRobot's own `dr_mem0_memory`.

Registered under the NAT config name `neo4j_agent_memory` so a workflow can
declare:

    memory:
      neo4j_memory:
        _type: neo4j_agent_memory
    workflow:
      _type: streaming_memory_agent
      memory_name: neo4j_memory
      inner_agent_name: neo4j_tool_calling_agent

Design notes:
- NAMS is conversation/session-scoped (not a free-form per-user memory
  store like mem0), so `user_id` from NAT's `MemoryItem`/`search()` calls is
  treated as the session key and mapped to a real NAMS-issued conversation
  UUID via the same local JSON cache used by `memory.py` (see that module's
  docstring for why NAMS conversation IDs cannot be client-chosen).
- `add_items()` persists each conversation turn via NAMS's
  `short_term.add_message()`.
- `search()` calls NAMS's `get_context()` and wraps the returned context
  string as a single synthetic `MemoryItem` (NAMS returns a pre-summarized
  context blob, not discrete scored memories, so there is exactly one
  result per call).
- When `neo4j-agent-memory` isn't installed or `MEMORY_API_KEY` is unset,
  `neo4j_agent_memory_client()` yields an `UnconfiguredMemoryEditor`, the
  same no-op pattern `dr_mem0_memory` uses, so a workflow can declare this
  memory backend unconditionally and enable it later via runtime parameters.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from nat.builder.builder import Builder
from nat.cli.register_workflow import register_memory
from nat.data_models.memory import MemoryBaseConfig
from nat.memory.interfaces import MemoryEditor
from nat.memory.models import MemoryItem

try:
    from . import memory as _nams
except ImportError:
    import memory as _nams  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

try:
    from neo4j_agent_memory import MemoryClient  # type: ignore[import]
    _HAS_NAMS = True
except ImportError:
    _HAS_NAMS = False


class Neo4jAgentMemoryConfig(MemoryBaseConfig, name="neo4j_agent_memory"):  # type: ignore[call-arg]
    """NAT memory backend backed by Neo4j Agent Memory (NAMS).

    Credentials are read from the standard NAMS environment variables
    (`MEMORY_API_KEY`, `MEMORY_WORKSPACE_ID`) — same as the rest of this
    repo — rather than being redeclared as config fields, so this plugin
    behaves identically whether it's driven from a `workflow.yaml` or from
    `custom.py`'s DRUM-based runtime-parameter loading.
    """


class UnconfiguredMemoryEditor(MemoryEditor):  # type: ignore[misc]
    """No-op memory backend returned when NAMS has no credentials configured."""

    async def add_items(self, items: list[MemoryItem], **kwargs: Any) -> None:
        return

    async def search(self, query: str, top_k: int = 5, **kwargs: Any) -> list[MemoryItem]:
        return []

    async def remove_items(self, **kwargs: Any) -> None:
        return


def is_memory_editor_configured(editor: MemoryEditor) -> bool:
    """Return ``False`` when `neo4j_agent_memory` yielded an unconfigured no-op editor."""
    return not isinstance(editor, UnconfiguredMemoryEditor)


class Neo4jMemoryEditor(MemoryEditor):  # type: ignore[misc]
    """Adapt NAMS's `MemoryClient` to NAT's `MemoryEditor` interface."""

    async def add_items(self, items: list[MemoryItem], **kwargs: Any) -> None:
        for item in items:
            session_key = item.user_id or kwargs.get("user_id") or "default_user"
            for message in item.conversation or []:
                role = message.get("role", "user")
                content = message.get("content", "")
                if not content:
                    continue
                try:
                    async with MemoryClient() as client:
                        real_id = await _nams._resolve_conversation_id(client, session_key)
                        await client.short_term.add_message(real_id, role, content)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("neo4j_agent_memory.add_items failed: %s", exc)

    async def search(self, query: str, top_k: int = 5, **kwargs: Any) -> list[MemoryItem]:
        session_key = kwargs.get("user_id") or "default_user"
        try:
            async with MemoryClient() as client:
                real_id = await _nams._resolve_conversation_id(client, session_key)
                context_text = await client.get_context(query, session_id=real_id, max_items=top_k)
        except Exception as exc:  # noqa: BLE001
            logger.warning("neo4j_agent_memory.search failed: %s", exc)
            return []

        if not context_text:
            return []
        return [MemoryItem(conversation=None, user_id=session_key, memory=context_text)]

    async def remove_items(self, **kwargs: Any) -> None:
        # NAMS's public SDK does not currently expose a conversation-delete
        # call; nothing to do beyond dropping the local session-key mapping.
        return


@register_memory(config_type=Neo4jAgentMemoryConfig)
async def neo4j_agent_memory_client(
    config: Neo4jAgentMemoryConfig, builder: Builder
) -> AsyncGenerator[MemoryEditor]:
    _ = config, builder
    if not _HAS_NAMS or not _nams.is_enabled():
        logger.info(
            "neo4j_agent_memory: not configured (install neo4j-agent-memory and set "
            "MEMORY_API_KEY / MEMORY_WORKSPACE_ID); memory operations are disabled"
        )
        yield UnconfiguredMemoryEditor()
        return

    yield Neo4jMemoryEditor()
