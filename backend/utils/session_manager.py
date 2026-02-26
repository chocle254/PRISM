"""
Session Manager
───────────────
Manages PRISM agent sessions using Firestore for persistence.
Each session has an orchestrator instance and conversation memory.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT_ID", "")
USE_FIRESTORE = os.environ.get("USE_FIRESTORE", "false").lower() == "true"

# In-memory fallback for dev
_in_memory_sessions: dict[str, dict] = {}


class SessionManager:
    """
    Creates and tracks PRISM sessions.
    Uses Firestore in production, in-memory in development.
    """

    def __init__(self):
        self._firestore_client = None
        if USE_FIRESTORE and GCP_PROJECT:
            try:
                from google.cloud import firestore
                self._firestore_client = firestore.AsyncClient(project=GCP_PROJECT)
                logger.info("SessionManager: Using Firestore")
            except Exception as e:
                logger.warning(f"Firestore unavailable, using in-memory: {e}")
        else:
            logger.info("SessionManager: Using in-memory store")

    async def create_session(self, user_id: str, context: dict = {}) -> str:
        """Create a new PRISM session and return session_id."""
        from agents.orchestrator import PRISMOrchestrator

        session_id = str(uuid.uuid4())
        orchestrator = PRISMOrchestrator(session_id=session_id)

        session_data = {
            "session_id": session_id,
            "user_id": user_id,
            "context": context,
            "orchestrator": orchestrator,
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
        }

        _in_memory_sessions[session_id] = session_data

        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection("sessions").document(session_id)
                await doc_ref.set({
                    "session_id": session_id,
                    "user_id": user_id,
                    "context": context,
                    "created_at": datetime.utcnow().isoformat(),
                    "status": "active",
                })
            except Exception as e:
                logger.error(f"Firestore session creation error: {e}")

        logger.info(f"Session created: {session_id} for user {user_id}")
        return session_id

    async def get_session(self, session_id: str) -> dict | None:
        """Retrieve a session by ID."""
        session = _in_memory_sessions.get(session_id)
        if session:
            session["last_active"] = datetime.utcnow().isoformat()
            return session
        return None

    async def end_session(self, session_id: str):
        """Clean up and remove a session."""
        session = _in_memory_sessions.pop(session_id, None)
        if session and "orchestrator" in session:
            await session["orchestrator"].on_disconnect()

        if self._firestore_client:
            try:
                doc_ref = self._firestore_client.collection("sessions").document(session_id)
                await doc_ref.update({"status": "ended", "ended_at": datetime.utcnow().isoformat()})
            except Exception as e:
                logger.error(f"Firestore session end error: {e}")

        logger.info(f"Session ended: {session_id}")

    async def cleanup_stale_sessions(self, max_age_hours: int = 2):
        """Remove sessions older than max_age_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        stale = [
            sid for sid, s in _in_memory_sessions.items()
            if datetime.fromisoformat(s["last_active"]) < cutoff
        ]
        for sid in stale:
            await self.end_session(sid)
        if stale:
            logger.info(f"Cleaned up {len(stale)} stale sessions")
