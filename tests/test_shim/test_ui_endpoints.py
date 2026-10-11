"""Unit tests for Mission Command UI REST and WebSocket endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auracode.shim.event_bus import MissionEventBus
from auracode.utils.journal import FileJournal


@pytest.mark.asyncio
async def test_fleet_workspaces_endpoint(client) -> None:
    """Verify /api/fleet/workspaces returns workspace status."""
    resp = await client.get("/api/fleet/workspaces")
    assert resp.status == 200
    data = await resp.json()
    assert "workspaces" in data
    assert len(data["workspaces"]) >= 1
    ws = data["workspaces"][0]
    assert "name" in ws
    assert "branch" in ws
    assert "dirty" in ws


@pytest.mark.asyncio
async def test_fleet_conflicts_endpoints(client, tmp_path: Path) -> None:
    """Verify /api/fleet/conflicts GET and POST resolution."""
    # Wire journal and event_bus on engine
    engine = client.app["engine"]
    engine._journal = FileJournal()
    engine.event_bus = MissionEventBus()

    # GET conflicts
    resp = await client.get("/api/fleet/conflicts")
    assert resp.status == 200
    data = await resp.json()
    assert "conflicts" in data

    # Create a conflict file in tmp_path
    cfile = tmp_path / "conflict.py"
    cfile.write_text(
        "<<<<<<< ours\nx = 1\n=======\nx = 2\n>>>>>>> theirs\n",
        encoding="utf-8",
    )

    # POST resolution for non-existent file
    bad_resp = await client.post("/api/fleet/conflicts", json={"file": "missing.py"})
    assert bad_resp.status == 200
    bad_data = await bad_resp.json()
    assert bad_data["success"] is False

    # Create a snapshot in journal so rollback has a target
    snap_id = engine._journal.create_snapshot("test_snap")

    # POST rollback
    rb_resp = await client.post("/api/fleet/rollback", json={"snapshot_id": snap_id})
    assert rb_resp.status == 200
    rb_data = await rb_resp.json()
    assert rb_data["success"] is True


@pytest.mark.asyncio
async def test_events_websocket_endpoint(client) -> None:
    """Verify /api/events connects and streams events over WebSocket."""
    engine = client.app["engine"]
    engine.event_bus = MissionEventBus()
    engine.event_bus.broadcast("test.started", {"step": 1})

    ws = await client.ws_connect("/api/events")
    msg = await ws.receive_str()
    data = json.loads(msg)
    assert data["type"] == "test.started"
    assert data["payload"]["step"] == 1

    await ws.close()


@pytest.mark.asyncio
async def test_ui_static_endpoints(client) -> None:
    """Verify Mission Command web UI assets are served with correct MIME types."""
    # Test index.html via /ui
    resp = await client.get("/ui")
    assert resp.status == 200
    text = await resp.text()
    assert "MISSION COMMAND" in text
    assert "deck-navigation" in text

    # Test styles.css
    css_resp = await client.get("/ui/styles.css")
    assert css_resp.status == 200
    css_text = await css_resp.text()
    assert "--bg-deep" in css_text

    # Test app.js
    js_resp = await client.get("/ui/app.js")
    assert js_resp.status == 200
    js_text = await js_resp.text()
    assert "connectWebSocket" in js_text
