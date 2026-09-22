"""
Neo4j Agent Memory (NAMS) integration for CrewAI.

Provides cross-session long-term memory, shared context across multi-agent crews,
and entity/preference recall using the `neo4j-agent-memory` package.

Supports two complementary integration modes:
1. `Neo4jCrewMemory`: CrewAI native Memory subclass backed by NAMS.
2. Custom NAMS BaseTools (`SearchMemoryTool`, `SaveMemoryFactTool`, `GetPreferencesTool`):
   Callable tools attached to CrewAI agents, allowing agents to explicitly query and store
   facts and context into the shared knowledge graph during execution.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from neo4j_agent_memory import MemoryClient, MemorySettings
    from neo4j_agent_memory.integrations.crewai import Neo4jCrewMemory, llm_provider_from_crewai
    _HAS_NAMS = True
except ImportError:
    _HAS_NAMS = False
    MemoryClient = None  # type: ignore[assignment,misc]
    MemorySettings = None  # type: ignore[assignment,misc]
    Neo4jCrewMemory = None  # type: ignore[assignment,misc]
    llm_provider_from_crewai = None  # type: ignore[assignment,misc]


def is_memory_configured() -> bool:
    """Check whether NAMS is enabled via environment variables or self-hosted settings."""
    if not _HAS_NAMS:
        return False
    # Check for NAMS API key or local Neo4j memory configuration
    has_api_key = bool(os.environ.get("MEMORY_API_KEY"))
    has_neo4j_uri = bool(os.environ.get("NEO4J_URI"))
    return has_api_key or has_neo4j_uri


def _run_coro(coro: Any) -> Any:
    """Helper to run an async coroutine synchronously inside CrewAI tools."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Running inside an active event loop (e.g. FastAPI / async runner)
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    else:
        return asyncio.run(coro)


# ── NAMS Client Factory ───────────────────────────────────────────────────────

_memory_client_instance: Any = None


def get_memory_client() -> Any:
    """Return a singleton MemoryClient instance if configured."""
    global _memory_client_instance
    if _memory_client_instance is not None:
        return _memory_client_instance

    if not _HAS_NAMS:
        return None

    try:
        # If MEMORY_API_KEY is present, MemoryClient uses the NAMS hosted backend
        _memory_client_instance = MemoryClient()
        return _memory_client_instance
    except Exception as e:
        logger.warning(f"Could not initialize NAMS MemoryClient: {e}")
        return None


# ── Custom CrewAI Memory Tools for Multi-Agent Shared Graph ────────────────────

class SearchMemoryInput(BaseModel):
    """Input schema for SearchMemoryTool."""
    query: str = Field(..., description="Query or topic to search for in long-term graph memory.")
    limit: int = Field(default=5, description="Maximum number of memories or facts to return.")


class SearchMemoryTool(BaseTool):
    name: str = "search_memory"
    description: str = (
        "Search cross-session long-term memory for previously learned facts, entity details, "
        "and findings about companies, industries, and user preferences."
    )
    args_schema: Type[BaseModel] = SearchMemoryInput

    def _run(self, query: str, limit: int = 5) -> str:
        client = get_memory_client()
        if client is None:
            return json.dumps({"status": "disabled", "message": "NAMS memory is not configured."})

        async def _search() -> list[str]:
            results = []
            try:
                # Search long-term entities and facts
                entities = await client.long_term.search_entities(query, limit=limit)
                for e in entities:
                    desc = getattr(e, "description", "")
                    name = getattr(e, "display_name", getattr(e, "name", "Entity"))
                    results.append(f"{name}: {desc}" if desc else name)
            except Exception as e:
                logger.debug(f"Entity search note: {e}")

            try:
                # Search past conversation messages
                messages = await client.short_term.search_messages(query, limit=limit)
                for m in messages:
                    results.append(f"Past Context: {getattr(m, 'content', str(m))}")
            except Exception as e:
                logger.debug(f"Message search note: {e}")

            return results[:limit]

        try:
            memories = _run_coro(_search())
            if not memories:
                return json.dumps({"memories": [], "message": f"No previous memories found for '{query}'"})
            return json.dumps({"memories": memories}, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to search memory: {e}"})


class SaveMemoryFactInput(BaseModel):
    """Input schema for SaveMemoryFactTool."""
    subject: str = Field(..., description="Subject of the fact (e.g. 'Google', 'AI Sector', 'Client').")
    predicate: str = Field(..., description="Relationship/predicate (e.g. 'acquired', 'invested_in', 'prefers').")
    content: str = Field(..., description="Detailed description or observation to remember.")


class SaveMemoryFactTool(BaseTool):
    name: str = "save_memory_fact"
    description: str = (
        "Store a verified fact or key analytical insight into the shared Neo4j long-term memory. "
        "Other agents in the crew and future sessions will be able to recall this fact."
    )
    args_schema: Type[BaseModel] = SaveMemoryFactInput

    def _run(self, subject: str, predicate: str, content: str) -> str:
        client = get_memory_client()
        if client is None:
            return json.dumps({"status": "disabled", "message": "NAMS memory is not configured."})

        async def _save() -> bool:
            await client.long_term.add_fact(subject, predicate, content)
            return True

        try:
            _run_coro(_save())
            return json.dumps({
                "status": "success",
                "message": f"Saved fact: ({subject}) -[{predicate}]-> '{content}' to Neo4j long-term memory."
            })
        except Exception as e:
            return json.dumps({"error": f"Failed to save fact to memory: {e}"})


class GetPreferencesInput(BaseModel):
    """Input schema for GetPreferencesTool."""
    category: str = Field(default="general", description="Category of preferences (e.g., 'analysis_style', 'report_format', 'general').")


class GetPreferencesTool(BaseTool):
    name: str = "get_preferences"
    description: str = "Retrieve user or crew formatting preferences and operational guidelines from memory."
    args_schema: Type[BaseModel] = GetPreferencesInput

    def _run(self, category: str = "general") -> str:
        client = get_memory_client()
        if client is None:
            return json.dumps({"status": "disabled", "message": "NAMS memory is not configured."})

        async def _get_prefs() -> list[str]:
            prefs = await client.long_term.search_preferences(category, limit=5)
            return [getattr(p, "preference", str(p)) for p in prefs]

        try:
            prefs = _run_coro(_get_prefs())
            return json.dumps({"category": category, "preferences": prefs}, indent=2)
        except Exception as e:
            return json.dumps({"error": f"Failed to retrieve preferences: {e}"})


def get_memory_tools() -> list[BaseTool]:
    """Return all NAMS Memory tools for multi-agent crew integration."""
    if not is_memory_configured():
        return []
    return [
        SearchMemoryTool(),
        SaveMemoryFactTool(),
        GetPreferencesTool(),
    ]


def build_crew_memory(crew_id: str = "default_crew") -> Any | None:
    """Build a Neo4jCrewMemory instance if NAMS is configured, or return None."""
    client = get_memory_client()
    if client is not None and Neo4jCrewMemory is not None:
        try:
            return Neo4jCrewMemory(memory_client=client, crew_id=crew_id)
        except Exception as e:
            logger.warning(f"Could not instantiate Neo4jCrewMemory: {e}")
    return None
