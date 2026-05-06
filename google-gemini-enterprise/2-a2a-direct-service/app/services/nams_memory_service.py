import logging
import httpx
import asyncio
from typing import Any
from google.genai import types as genai_types
from google.adk.memory.base_memory_service import SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.memory.base_memory_service import BaseMemoryService

class NAMSMemoryService(BaseMemoryService):
    """Lightweight async client to interact with NAMS via REST using GraphRAG."""

    def __init__(self, api_key: str, base_url: str = "https://memory.neo4jlabs.com/v1", user_id: str = None):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self._client = httpx.AsyncClient(
            timeout=30.0, 
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

    def _extract_text(self, content: Any) -> str:
        """Safely extracts raw text from various content payload structures."""
        if isinstance(content, dict) and 'parts' in content:
            try:
                return content['parts'][0].get('text', '')
            except (IndexError, AttributeError):
                return ""
        return str(content) if content is not None else ""

    def _get_extracted_messages(self, session: Any) -> list[dict]:
        """Extracts messages while strictly filtering out all ADK tool calls and error noise."""
        messages = []

        raw_msgs = getattr(session, "events", None) or getattr(session, "messages", None) or (session.get("messages") if isinstance(session, dict) else session)
        if not isinstance(raw_msgs, list):
            return []

        for msg in raw_msgs:
            content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
            if not content:
                continue

            is_tool_noise = False

            if hasattr(content, "parts"):
                for part in content.parts:
                    if getattr(part, "function_call", None) or getattr(part, "function_response", None):
                        is_tool_noise = True
                        break
            elif isinstance(content, dict) and 'parts' in content:
                for part in content['parts']:
                    if any(key in part for key in ['functionCall', 'functionResponse', 'function_call', 'function_response']):
                        is_tool_noise = True
                        break

            if is_tool_noise:
                continue 

            text = self._extract_text(content)
            if not text or len(text.strip()) < 2:
                continue

            role = getattr(msg, "role", None) or getattr(msg, "author", "user")
            if hasattr(role, "value"):
                role = role.value
            elif isinstance(msg, dict):
                role = msg.get("role", "user")

            messages.append({"role": str(role), "content": text})

        return messages

    def _build_conversation_payload(self, app_name: str, user_id: str, session_id: str = None) -> dict:
        """Builds a strictly compliant JSON payload for the POST /conversations API."""
        payload = {
            "userId": user_id,
            "metadata": {
                "appName": app_name
            }
        }
        if session_id:
            payload["metadata"]["sessionId"] = session_id

        if payload["userId"] is None:
            del payload["userId"]

        return payload

    async def search_memory(self, *, app_name: str, user_id: str, query: str, limit: int = 5, threshold: float = 0.3):
        """Executes a semantic vector search across extracted entities."""
        logging.info(f"[nams] Executing vector entity search for query: '{query}'")
        try:
            search_url = f"{self.base_url}/entities/search"

            payload = {
                "userId": user_id,
                "query": query,
                "type": "vector",
                "limit": limit
            }
            if payload.get("userId") is None:
                del payload["userId"]
                
            resp = await self._client.post(search_url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            entities = data.get("entities", [])
            memories = []

            for ent in entities:
                name = ent.get("name", "")
                desc = ent.get("description", "")

                if name:
                    text = f"Known Entity: {name}"
                    if desc:
                        text += f" (Context: {desc})"

                    part = genai_types.Part.from_text(text=text)
                    if MemoryEntry is not None:
                        memories.append(MemoryEntry(content=genai_types.Content(parts=[part]), author="system"))
                    else:
                        memories.append({"content": {"parts": [{"text": text}]}, "author": "system"})

            logging.info(f"[nams] Retrieved {len(memories)} entities from vector search")

            if SearchMemoryResponse is not None:
                return SearchMemoryResponse(memories=memories)
            return {"memories": memories}

        except Exception as e:
            logging.error(f"[nams] Vector entity search failed: {e}")
            if SearchMemoryResponse is not None:
                return SearchMemoryResponse(memories=[])
            return {"memories": []}

    async def add_session_to_memory(self, session):
        """Posts session messages to the correct user namespace, dropping tool noise."""
        logging.info("[nams] Adding session to memory")

        extracted_msgs = self._get_extracted_messages(session)

        if not extracted_msgs:
            logging.info("[nams] No valid text messages found after filtering tool noise.")
            return

        app_name = getattr(session, 'app_name', None) or "neo4j_a2a_app"
        user_id = getattr(session, 'user_id', None) or self.user_id
        session_id = getattr(session, 'id', None)

        payload = self._build_conversation_payload(app_name, user_id, session_id)

        try:
            resp = await self._client.post(f"{self.base_url}/conversations", json=payload)
            resp.raise_for_status()
            conv_id = resp.json().get("id")

            logging.info(f"[nams] Created NAMS conversation {conv_id} mapped to userId: {user_id}")

            for m in extracted_msgs:
                role = m.get('role', 'user')
                content = m.get('content', '')
                text = self._extract_text(content)

                if not text: 
                    continue

                await self._client.post(
                    f"{self.base_url}/conversations/{conv_id}/messages", 
                    json={"role": role, "content": text}
                )
            logging.info(f"[nams] Successfully pushed {len(extracted_msgs)} clean session messages to NAMS")

        except Exception as e:
            logging.error(f"[nams] Failed to add session to memory: {e}")

    async def add_memory(self, *, app_name: str, user_id: str, content: Any, **kwargs):
        """Allows the agent to explicitly save a high-priority fact mid-conversation."""
        logging.info(f"[nams] Agent explicitly called add_memory for user: {user_id}")

        text = self._extract_text(content)
        if not text:
            return

        try:
            payload = self._build_conversation_payload(app_name, user_id)

            resp = await self._client.post(f"{self.base_url}/conversations", json=payload)
            resp.raise_for_status()
            conv_id = resp.json().get("id")

            await self._client.post(
                f"{self.base_url}/conversations/{conv_id}/messages", 
                json={"role": "user", "content": f"Please remember this explicitly: {text}"}
            )
            logging.info(f"[nams] Successfully remembered explicit fact for {user_id}")

        except Exception as e:
            logging.error(f"[nams] Failed to execute add_memory: {e}")

    async def add_events_to_memory(self, *, app_name: str, user_id: str, events: list[Any], **kwargs):
        """Processes a sequence of agent events for event-driven runners."""
        logging.info(f"[nams] Adding events to memory for user {user_id}")

        if not events:
            return

        try:
            payload = self._build_conversation_payload(app_name, user_id)

            resp = await self._client.post(f"{self.base_url}/conversations", json=payload)
            resp.raise_for_status()
            conv_id = resp.json().get("id")

            added_count = 0
            for event in events:
                content = getattr(event, "content", None) or event
                text = self._extract_text(content)
                if not text:
                    continue

                author = getattr(event, "author", None)
                role = str(author) if author else "system"

                await self._client.post(
                    f"{self.base_url}/conversations/{conv_id}/messages", 
                    json={"role": role, "content": text}
                )
                added_count += 1

            logging.info(f"[nams] Successfully pushed {added_count} events to NAMS for user {user_id}")

        except Exception as e:
            logging.error(f"[nams] Failed to execute add_events_to_memory: {e}")

    async def close(self):
        await self._client.aclose()