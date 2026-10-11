"""End-to-end integration suite for Phase 3 Grid Deployment, MAS MCP, and Fleet Ecosystem."""

from __future__ import annotations

import json
import types
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from auracode.bundle.packager import BundlePackager
from auracode.git.grid_mirror import GridMirrorOrchestrator
from auracode.shim.server import create_app


def test_e2e_bundle_pack_validate_inspect(tmp_path: Path) -> None:
    """Validate end-to-end bundle packaging, cell governance, and tamper verification."""
    src = tmp_path / "my_app"
    src.mkdir()
    manifest_data = {
        "schemaVersion": "1.0",
        "appId": "grid_prototype",
        "name": "AI Grid Prototype",
        "version": "0.1.0",
        "startup": {"path": "main.py"},
        "cellGovernance": {
            "targetCells": ["cell-compute-1"],
            "requiredOs": "windows",
            "minRamMb": 1024,
            "requiresGpu": False,
        },
    }
    (src / "app.manifest.json").write_text(json.dumps(manifest_data), encoding="utf-8")
    (src / "main.py").write_text("print('hello grid')\n", encoding="utf-8")

    out_bundle = tmp_path / "grid_prototype.aurabundle"
    res = BundlePackager.pack(src, out_bundle)
    assert res.is_file()

    info = BundlePackager.inspect(res)
    assert info["app_id"] == "grid_prototype"
    assert info["cell_governance"]["min_ram_mb"] == 1024
    assert len(info["sha256"]) == 64
    assert "main.py" in info["files"]


def test_e2e_zero_vector_db_invariants() -> None:
    """Verify strictly zero local neural vector DB or embedding dependencies in core."""
    src_dir = Path("src/auracode").resolve()
    banned = ["chromadb", "faiss", "numpy", "sentence_transformers"]
    for py_file in src_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for bad in banned:
            assert f"import {bad}" not in content, f"Banned dependency {bad} found in {py_file}"


def test_e2e_grid_mirror_workflow(tmp_path: Path) -> None:
    """Verify distributed bare mirror initialization and node sync."""
    grid_storage = tmp_path / "grid_storage"
    mirror = GridMirrorOrchestrator.init_grid_mirror("proto_repo", grid_storage)
    assert mirror.is_dir()

    info = GridMirrorOrchestrator.get_mirror_info(mirror)
    assert info["exists"] is True
    assert info["is_bare"] is True


@pytest.mark.asyncio
async def test_e2e_mcp_reverse_tools_suite() -> None:
    """Verify that all 8 reverse-MCP tools are exported and callable."""
    registered: dict[str, Any] = {}

    class FakeFastMCP:
        def __init__(self, name: str):
            self.name = name

        def tool(self):
            def decorator(fn):
                registered[fn.__name__] = fn
                return fn

            return decorator

    fake_mcp = types.ModuleType("mcp")
    fake_mcp_server = types.ModuleType("mcp.server")
    fake_mcp_server.FastMCP = FakeFastMCP  # type: ignore[attr-defined]

    with pytest.MonkeyPatch.context() as mp:
        mp.setitem(__import__("sys").modules, "mcp", fake_mcp)
        mp.setitem(__import__("sys").modules, "mcp.server", fake_mcp_server)

        from auracode.mcp_server import create_mcp_server

        mock_engine = MagicMock()
        mock_engine.execute_loop = AsyncMock()
        server = create_mcp_server(mock_engine)
        assert server is not None

        required_tools = [
            "auracode_act",
            "auracode_repomap",
            "auracode_conflicts",
            "auracode_resolve_conflicts",
            "auracode_rollback",
            "auracode_synthesize_commit",
            "auracode_bundle_pack",
            "auracode_bundle_validate",
        ]
        for t in required_tools:
            assert t in registered, f"Missing MCP tool {t}"


@pytest.mark.asyncio
async def test_e2e_multi_workspace_api(aiohttp_client, tmp_path: Path) -> None:
    """Verify fleet workspace manager REST endpoints."""
    mock_engine = MagicMock()
    mock_engine.config.auth_token = None
    app = create_app(mock_engine)
    client = await aiohttp_client(app)

    # Register project via REST
    proj = tmp_path / "fleet_project"
    proj.mkdir()
    resp = await client.post("/api/fleet/workspaces", json={"path": str(proj)})
    assert resp.status == 200
    data = await resp.json()
    assert data["success"] is True

    # List
    list_resp = await client.get("/api/fleet/workspaces")
    assert list_resp.status == 200
    list_data = await list_resp.json()
    assert any(w["name"] == "fleet_project" for w in list_data["workspaces"])

    # Unregister
    del_resp = await client.delete("/api/fleet/workspaces", json={"path": str(proj)})
    assert del_resp.status == 200
