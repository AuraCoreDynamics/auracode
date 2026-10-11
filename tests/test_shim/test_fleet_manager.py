"""Unit tests for FleetWorkspaceManager and multi-workspace endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from auracode.engine.fleet_manager import FleetWorkspaceManager
from auracode.shim.server import create_app


def test_fleet_workspace_manager_lifecycle(tmp_path: Path) -> None:
    persist_file = tmp_path / "workspaces.json"
    mgr = FleetWorkspaceManager(persistence_file=persist_file)

    # Initial state has current dir
    paths = mgr.list_paths()
    assert len(paths) >= 1

    # Register project A
    proj_a = tmp_path / "project_a"
    proj_a.mkdir()
    res_a = mgr.register(proj_a)
    assert res_a["name"] == "project_a"
    assert res_a["path"] == str(proj_a)
    assert str(proj_a) in mgr.list_paths()

    # Verify persisted to disk
    assert persist_file.exists()
    saved = json.loads(persist_file.read_text(encoding="utf-8"))
    assert str(proj_a) in saved

    # Unregister project A
    ok = mgr.unregister(proj_a)
    assert ok is True
    assert str(proj_a) not in mgr.list_paths()


def test_fleet_workspace_manager_invalid_path(tmp_path: Path) -> None:
    mgr = FleetWorkspaceManager(persistence_file=tmp_path / "workspaces.json")
    with pytest.raises(ValueError, match="does not exist"):
        mgr.register(tmp_path / "nonexistent")


@pytest.mark.asyncio
async def test_fleet_workspace_manager_async_list(tmp_path: Path) -> None:
    proj_b = tmp_path / "project_b"
    proj_b.mkdir()
    mgr = FleetWorkspaceManager(persistence_file=tmp_path / "workspaces.json")
    mgr.register(proj_b)

    workspaces = await mgr.list_workspaces()
    assert any(ws["name"] == "project_b" for ws in workspaces)


@pytest.mark.asyncio
async def test_fleet_api_endpoints(aiohttp_client, tmp_path: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.config.auth_token = None
    app = create_app(mock_engine)

    client = await aiohttp_client(app)

    # GET /api/fleet/workspaces
    resp = await client.get("/api/fleet/workspaces")
    assert resp.status == 200
    data = await resp.json()
    assert "workspaces" in data

    # POST /api/fleet/workspaces
    proj_c = tmp_path / "project_c"
    proj_c.mkdir()
    post_resp = await client.post("/api/fleet/workspaces", json={"path": str(proj_c)})
    assert post_resp.status == 200
    post_data = await post_resp.json()
    assert post_data["success"] is True

    # DELETE /api/fleet/workspaces
    del_resp = await client.delete("/api/fleet/workspaces", json={"path": str(proj_c)})
    assert del_resp.status == 200
    del_data = await del_resp.json()
    assert del_data["success"] is True


@pytest.mark.asyncio
async def test_auth_token_middleware(aiohttp_client) -> None:
    mock_engine = MagicMock()
    mock_engine.config.auth_token = "secret-token-123"
    app = create_app(mock_engine)

    client = await aiohttp_client(app)

    # Without token -> 401
    resp_unauth = await client.get("/api/fleet/workspaces")
    assert resp_unauth.status == 401

    # With Bearer token -> 200
    resp_auth = await client.get(
        "/api/fleet/workspaces",
        headers={"Authorization": "Bearer secret-token-123"},
    )
    assert resp_auth.status == 200

    # UI assets remain publicly accessible without auth token
    resp_ui = await client.get("/ui")
    assert resp_ui.status in (200, 404)
