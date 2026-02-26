"""
Conversation Memory
────────────────────
Manages conversation history and context recall for PRISM sessions.
Stores in Firestore with in-memory fallback.
"""

import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "")
USE_FIRESTORE = os.environ.get("USE_FIRESTORE", "false").lower() == "true"

_memory_store: dict[str, list] = {}


class ConversationMemory:
    """
    Stores and retrieves conversation history for a PRISM session.
    
    Supports:
    - Adding user/assistant messages
    - Recalling relevant context by query
    - Summarizing long conversations
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._firestore_client = None
        _memory_store[session_id] = []

        if USE_FIRESTORE and GCP_PROJECT:
            try:
                from google.cloud import firestore
                self._firestore_client = firestore.AsyncClient(project=GCP_PROJECT)
            except Exception as e:
                logger.warning(f"Firestore unavailable for memory: {e}")

    async def add_user_message(self, text: str, metadata: dict = {}):
        """Record a user message."""
        entry = {
            "role": "user",
            "content": text,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }
        _memory_store[self.session_id].append(entry)
        await self._persist(entry)

    async def add_assistant_message(self, text: str, metadata: dict = {}):
        """Record an assistant message."""
        entry = {
            "role": "assistant",
            "content": text,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
        }
        _memory_store[self.session_id].append(entry)
        await self._persist(entry)

    async def get_history(self, last_n: int = 20) -> list[dict]:
        """Get the last N messages in the conversation."""
        history = _memory_store.get(self.session_id, [])
        return history[-last_n:]

    async def recall(self, query: str) -> dict:
        """
        Find the most relevant past context for a given query.
        Simple keyword matching — in production, use vector similarity.
        """
        history = _memory_store.get(self.session_id, [])
        if not history:
            return {"found": False, "context": ""}

        query_lower = query.lower()
        relevant = []

        for entry in history:
            content_lower = entry["content"].lower()
            # Simple relevance: count query word overlaps
            words = set(query_lower.split())
            overlap = sum(1 for w in words if w in content_lower)
            if overlap > 0:
                relevant.append((overlap, entry))

        relevant.sort(key=lambda x: x[0], reverse=True)
        top = [e for _, e in relevant[:3]]

        if not top:
            # Return recent context as fallback
            top = history[-3:]

        context_text = "\n".join(
            f"{e['role'].upper()}: {e['content']}" for e in top
        )

        return {
            "found": bool(top),
            "context": context_text,
            "message_count": len(history),
        }

    async def get_summary(self) -> str:
        """Get a brief summary of the conversation so far."""
        history = _memory_store.get(self.session_id, [])
        if not history:
            return "No conversation yet"

        user_messages = [e["content"] for e in history if e["role"] == "user"]
        if not user_messages:
            return "No user messages"

        return f"Conversation with {len(history)} messages. User has asked about: {', '.join(user_messages[-3:])}"

    async def clear(self):
        """Clear all memory for this session."""
        _memory_store[self.session_id] = []

    async def _persist(self, entry: dict):
        """Persist a message to Firestore."""
        if not self._firestore_client:
            return
        try:
            col = self._firestore_client.collection("sessions").document(
                self.session_id
            ).collection("messages")
            await col.add(entry)
        except Exception as e:
            logger.debug(f"Memory persist error (non-critical): {e}")
