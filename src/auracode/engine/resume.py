"""Resume context building — staleness-aware message preparation for session continuation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest

#: Sessions older than this threshold are considered stale; history is excluded.
_DEFAULT_STALENESS_THRESHOLD = timedelta(minutes=5)


class ResumeContextBuilder(Protocol):
    """Extension point for building the message list from a session context.

    Implementations decide whether to include prior history (e.g., based on
    session staleness), augment with retrieval hints, or inject system prompts.
    """

    def build(
        self,
        session: SessionContext,
        request: EngineRequest,
    ) -> list[dict[str, Any]]:
        """Return an ordered list of role/content message dicts for the LLM."""
        ...


class DefaultResumeContextBuilder:
    """Default staleness-aware implementation of :class:`ResumeContextBuilder`.

    Includes prior history only when the session was updated within the staleness
    threshold (default: 5 minutes).  The comparison is timezone-aware:
    ``session.updated_at`` is stored as UTC, compared against ``datetime.now(timezone.utc)``.
    """

    def __init__(self, staleness_threshold: timedelta = _DEFAULT_STALENESS_THRESHOLD) -> None:
        self._threshold = staleness_threshold

    def build(
        self,
        session: SessionContext,
        request: EngineRequest,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []

        # Ensure the session timestamp is offset-aware before comparing.
        updated_at = session.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)

        age = datetime.now(UTC) - updated_at
        is_stale = age > self._threshold

        if not is_stale:
            messages.extend(session.history)

        messages.append({"role": "user", "content": request.prompt})
        return messages
