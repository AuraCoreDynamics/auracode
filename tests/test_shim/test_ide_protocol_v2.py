"""Unit tests for IDE Protocol V2 and Spyder companion bridge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auracode.adapters.spyder_bridge import SpyderAuraCodeBridge
from auracode.models.request import EngineResponse
from auracode.shim.ide_protocol import (
    ActCompleted,
    ActProgress,
    ActRequest,
    ConflictsDetected,
    RepoMapRequest,
    RepoMapResponse,
    ResolveConflictRequest,
)
from auracode.shim.server import create_app


def test_v2_protocol_models() -> None:
    act_req = ActRequest(prompt="fix bugs", verify_command="pytest", max_attempts=2)
    assert act_req.type == "ide.act_request"
    assert act_req.prompt == "fix bugs"
    assert act_req.max_attempts == 2

    act_prog = ActProgress(status="running", phase="verifying", attempt=2)
    assert act_prog.type == "ide.act_progress"
    assert act_prog.attempt == 2

    act_comp = ActCompleted(
        status="PASSED",
        snapshot_id="snap-123",
        remediations_count=1,
        output="fixed",
    )
    assert act_comp.type == "ide.act_completed"
    assert act_comp.snapshot_id == "snap-123"

    res_req = ResolveConflictRequest(file_path="src/main.py")
    assert res_req.type == "ide.resolve_conflict_request"
    assert res_req.file_path == "src/main.py"

    conf = ConflictsDetected(count=2, files=["a.py", "b.py"])
    assert conf.count == 2

    map_req = RepoMapRequest(workspace_root=".")
    assert map_req.workspace_root == "."

    map_resp = RepoMapResponse(workspace_root=".", map_text="class A: pass", symbol_count=1)
    assert map_resp.symbol_count == 1


@pytest.mark.asyncio
async def test_ide_websocket_v2_repomap(aiohttp_client, tmp_path: Path) -> None:
    mock_engine = MagicMock()
    mock_engine.config.auth_token = None
    app = create_app(mock_engine)
    client = await aiohttp_client(app)

    # Create dummy python file in tmp_path
    (tmp_path / "mod.py").write_text("class Demo:\n    def run(self):\n        pass\n")

    ws = await client.ws_connect("/ws/ide")
    await ws.send_json(
        {
            "type": "ide.repomap_request",
            "workspace_root": str(tmp_path),
            "max_chars": 2048,
        }
    )

    msg = await ws.receive_json()
    assert msg["type"] == "ide.repomap_response"
    assert "Demo" in msg["map_text"]
    assert msg["symbol_count"] >= 1
    await ws.close()


@pytest.mark.asyncio
async def test_ide_websocket_v2_act_loop(aiohttp_client) -> None:
    mock_engine = MagicMock()
    mock_engine.config.auth_token = None

    mock_loop_result = MagicMock()
    mock_loop_result.status = "PASSED"
    mock_loop_result.snapshot_id = "snap-test"
    mock_loop_result.remediations = []
    mock_loop_result.final_response = EngineResponse(
        request_id="test",
        content="Code healed",
        model_used="mock",
    )
    mock_engine.execute_loop = AsyncMock(return_value=mock_loop_result)

    app = create_app(mock_engine)
    client = await aiohttp_client(app)

    ws = await client.ws_connect("/ws/ide")
    await ws.send_json(
        {
            "type": "ide.act_request",
            "prompt": "fix issue",
            "verify_command": "pytest",
            "max_attempts": 1,
        }
    )

    # First receive progress
    msg1 = await ws.receive_json()
    assert msg1["type"] == "ide.act_progress"
    assert msg1["status"] == "running"

    # Next receive completed
    msg2 = await ws.receive_json()
    assert msg2["type"] == "ide.act_completed"
    assert msg2["status"] == "PASSED"
    assert msg2["snapshot_id"] == "snap-test"
    assert msg2["output"] == "Code healed"
    await ws.close()


def test_spyder_bridge(tmp_path: Path) -> None:
    bridge = SpyderAuraCodeBridge(workspace_root=tmp_path)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n")

    repo_map = bridge.get_repo_map()
    assert "add" in repo_map

    with patch("webbrowser.open") as mock_open:
        res = bridge.launch_ui()
        mock_open.assert_called_once()
        assert "8741/ui" in res
