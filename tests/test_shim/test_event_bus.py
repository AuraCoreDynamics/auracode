"""Unit tests for MissionEventBus telemetry broadcasting."""

from __future__ import annotations

import asyncio

import pytest

from auracode.shim.event_bus import MissionEventBus


@pytest.mark.asyncio
async def test_event_bus_broadcast_and_subscribe() -> None:
    """Verify MissionEventBus delivers broadcast events to async subscribers."""
    bus = MissionEventBus(max_history=10)
    assert bus.subscriber_count == 0

    sub = bus.subscribe()
    # Trigger first iteration to enter the try block and register subscriber
    task = asyncio.create_task(anext(sub))
    await asyncio.sleep(0.01)
    assert bus.subscriber_count == 1

    bus.broadcast("agent.step_started", {"request_id": "r1", "attempt": 1})
    evt1 = await task
    assert evt1["type"] == "agent.step_started"

    bus.broadcast("verification.executed", {"command": "pytest", "attempt": 1})
    evt2 = await anext(sub)
    assert evt2["type"] == "verification.executed"

    await sub.aclose()
    assert bus.subscriber_count == 0


def test_event_bus_ring_buffer_capacity() -> None:
    """Verify MissionEventBus ring buffer retains up to max_history entries."""
    bus = MissionEventBus(max_history=5)
    for i in range(10):
        bus.broadcast("event.ping", {"index": i})

    recent = bus.get_recent_events(limit=10)
    assert len(recent) == 5
    assert recent[0]["payload"]["index"] == 5
    assert recent[-1]["payload"]["index"] == 9

    bus.clear()
    assert len(bus.get_recent_events()) == 0
