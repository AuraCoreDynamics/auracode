"""In-memory session manager."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from auracode.engine.resume import DefaultResumeContextBuilder, ResumeContextBuilder
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse


class SessionManager:
    """Manages coding sessions with in-memory storage."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionContext] = {}

    def create(self, working_directory: str) -> SessionContext:
        """Create a new session and return its context."""
        session_id = uuid.uuid4().hex
        ctx = SessionContext(
            session_id=session_id,
            working_directory=working_directory,
        )
        self._sessions[session_id] = ctx
        return ctx

    def get(self, session_id: str) -> SessionContext | None:
        """Retrieve an existing session, or None if not found."""
        return self._sessions.get(session_id)

    def prepare_messages(
        self,
        session_id: str,
        request: EngineRequest,
        builder: ResumeContextBuilder | None = None,
    ) -> list[dict[str, Any]]:
        """Return an ordered message list for the LLM, applying staleness logic.

        Uses *builder* when provided; falls back to :class:`DefaultResumeContextBuilder`.
        Raises :exc:`KeyError` if the session does not exist.
        """
        ctx = self._sessions.get(session_id)
        if ctx is None:
            raise KeyError(f"Session {session_id!r} not found")

        effective_builder: ResumeContextBuilder = builder or DefaultResumeContextBuilder()
        return effective_builder.build(ctx, request)

    def update(
        self,
        session_id: str,
        request: EngineRequest,
        response: EngineResponse,
        journal: list[dict[str, Any]] | None = None,
    ) -> SessionContext:
        """Append a request/response exchange to the session history.

        Returns the updated SessionContext.  Raises KeyError if the
        session does not exist.
        """
        ctx = self._sessions.get(session_id)
        if ctx is None:
            raise KeyError(f"Session {session_id!r} not found")

        new_entry = {"role": "user", "content": request.prompt}
        assistant_entry = {"role": "assistant", "content": response.content}

        update_fields: dict[str, Any] = {
            "history": [*ctx.history, new_entry, assistant_entry],
            "updated_at": datetime.now(UTC),
        }
        if journal:
            update_fields["journal"] = [*ctx.journal, *journal]

        updated = ctx.model_copy(update=update_fields)
        self._sessions[session_id] = updated
        return updated

    def close(self, session_id: str) -> None:
        """Remove a session from the store.  No-op if absent."""
        self._sessions.pop(session_id, None)
