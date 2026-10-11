"""Mission Event Bus — Asynchronous WebSocket telemetry stream for Mission Command."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from collections.abc import AsyncIterator
from typing import Any

logger = logging.getLogger(__name__)


class MissionEventBus:
    """In-memory event bus broadcasting agent and system telemetry to web subscribers."""

    def __init__(self, max_history: int = 200) -> None:
        self.max_history = max_history
        self._history: deque[dict[str, Any]] = deque(maxlen=max_history)
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @property
    def subscriber_count(self) -> int:
        """Return the number of actively connected subscribers."""
        return len(self._subscribers)

    def broadcast(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Broadcast an event to all connected subscriber queues and record in history.

        Safe to invoke from both the main asyncio thread and background worker threads.
        """
        event: dict[str, Any] = {
            "id": uuid.uuid4().hex[:8],
            "type": event_type,
            "timestamp": time.time(),
            "payload": payload,
        }
        self._history.append(event)

        for q in list(self._subscribers):
            try:
                # If queue belongs to a running loop in another thread, use threadsafe call
                q_loop = getattr(q, "_loop", None)
                try:
                    curr_loop = asyncio.get_running_loop()
                except RuntimeError:
                    curr_loop = None

                if q_loop and curr_loop != q_loop and q_loop.is_running():
                    q_loop.call_soon_threadsafe(q.put_nowait, event)
                else:
                    q.put_nowait(event)
            except Exception as exc:
                logger.debug(f"Failed to deliver event to subscriber queue: {exc}")

        return event

    async def subscribe(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to the event stream, yielding events as they are broadcast."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            self._subscribers.discard(q)

    def get_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent events from the ring buffer up to limit."""
        events = list(self._history)
        return events[-limit:] if limit < len(events) else events

    def clear(self) -> None:
        """Clear all historical events."""
        self._history.clear()
