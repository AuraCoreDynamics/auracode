"""End-to-end integration tests for Mission Command orchestration and flight deck."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from auracode.engine.core import AuraCodeEngine
from auracode.git.conflict_resolver import MergeConflictResolver
from auracode.git.poller import GitMirrorPoller
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, RequestIntent
from auracode.models.verification import RemediationBudget, VerificationCommand
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult
from auracode.shim.event_bus import MissionEventBus
from auracode.shim.server import create_app
from auracode.utils.journal import FileJournal


class _SequentialLoopRouter(BaseRouterBackend):
    """Router returning sequential responses for testing self-healing turns."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_count = 0

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        idx = min(self._call_count, len(self._responses) - 1)
        resp_text = self._responses[idx]
        self._call_count += 1
        return RouteResult(content=resp_text, model_used="test-mock")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_mission_command_agent_loop_self_healing_integration(tmp_path: Path) -> None:
    """Verify autonomous self-healing agent loop emits telemetry events and repairs bugs."""
    event_bus = MissionEventBus()
    config = AuraCodeConfig()
    config.permissions.allow_file_write = True
    config.permissions.allow_shell_commands = True

    # First turn outputs code with a bug (x = 1), second turn fixes bug (x = 42)
    turn1_payload = (
        '{"plan":"initialize variable","modifications":['
        '{"file_path":"answer.py","modification_type":"full_rewrite",'
        '"language":"python","content":"x = 1\\n"}]}'
    )
    turn2_payload = (
        '{"plan":"fix variable value","modifications":['
        '{"file_path":"answer.py","modification_type":"full_rewrite",'
        '"language":"python","content":"x = 42\\n"}]}'
    )

    router = _SequentialLoopRouter([turn1_payload, turn2_payload])
    engine = AuraCodeEngine(config, router, event_bus=event_bus)

    # Verification checks that answer.py defines x == 42
    test_script = tmp_path / "verify_answer.py"
    test_script.write_text(
        "import sys\nfrom answer import x\nif x != 42:\n    sys.exit(1)\n",
        encoding="utf-8",
    )

    verif_cmd = f'"{sys.executable}" "{test_script}"'
    req = EngineRequest(
        request_id="int_req_01",
        intent=RequestIntent.EDIT_CODE,
        prompt="Create answer.py with x = 42",
        adapter_name="opencode",
        context=SessionContext(session_id="s1", working_directory=str(tmp_path)),
    )

    result = await engine.execute_loop(
        req,
        verification=VerificationCommand(command=verif_cmd, working_directory=str(tmp_path)),
        budget=RemediationBudget(max_attempts=3),
    )

    assert result.status == "success"
    assert len(result.remediations) == 2
    assert result.remediations[0].verification.passed is False
    assert result.remediations[1].verification.passed is True

    # Verify answer.py content
    ans_file = tmp_path / "answer.py"
    assert ans_file.is_file()
    assert "x = 42" in ans_file.read_text(encoding="utf-8")

    # Verify event stream captured the telemetry
    events = event_bus.get_recent_events(limit=50)
    event_types = [e["type"] for e in events]
    assert "journal.snapshot_created" in event_types
    assert "agent.step_started" in event_types
    assert "verification.executed" in event_types
    assert "verification.result" in event_types
    assert "agent.step_completed" in event_types

    # Test transactional rollback restores snapshot
    assert result.snapshot_id is not None
    restored = engine._journal.rollback_snapshot(result.snapshot_id)
    assert any("answer.py" in str(p) for p in restored)
    assert not ans_file.exists()


def test_mission_command_git_preflight_gate_integration(tmp_path: Path) -> None:
    """Verify failing pre-flight test commands strictly block lifecycle restart."""
    mock_mirror = MagicMock()
    mock_lifecycle = MagicMock()
    mock_mirror.storage_path = tmp_path

    event_bus = MissionEventBus()
    poller = GitMirrorPoller(
        mock_mirror,
        mock_lifecycle,
        preflight_command=f'"{sys.executable}" -c "import sys; sys.exit(1)"',
        event_bus=event_bus,
    )

    repo_dir = tmp_path / "app.git"
    repo_dir.mkdir()

    passed = poller._run_preflight(repo_dir, "abc1234", "test_app")
    assert passed is False
    mock_lifecycle.trigger_restart.assert_not_called()

    # Verify preflight event broadcasted failure
    events = event_bus.get_recent_events(limit=10)
    assert any(
        e["type"] == "git.preflight_result" and e["payload"]["passed"] is False for e in events
    )


@pytest.mark.asyncio
async def test_mission_command_conflict_resolver_integration(tmp_path: Path) -> None:
    """Verify 3-way merge conflict resolver synthesizes clean conflict-free code."""
    event_bus = MissionEventBus()
    config = AuraCodeConfig()
    resolved_text = "def compute():\n    return 42\n"

    router = _SequentialLoopRouter([resolved_text])
    engine = AuraCodeEngine(config, router, event_bus=event_bus)
    journal = FileJournal()

    target_file = tmp_path / "logic.py"
    target_file.write_text(
        "def compute():\n<<<<<<< HEAD\n    return 40\n=======\n    return 42\n>>>>>>> feature\n",
        encoding="utf-8",
    )

    resolver = MergeConflictResolver(engine, journal=journal)
    success, msg = await resolver.resolve_file(target_file)

    assert success is True
    assert "Successfully resolved" in msg
    content = target_file.read_text(encoding="utf-8")
    assert content == resolved_text
    assert "<<<<<<<" not in content

    # Verify event bus emitted conflict events
    events = event_bus.get_recent_events(limit=10)
    event_types = [e["type"] for e in events]
    assert "git.conflict_detected" in event_types
    assert "git.conflict_resolved" in event_types


@pytest.mark.asyncio
async def test_mission_command_ui_flight_deck_integration(aiohttp_client) -> None:
    """Verify Mission Command UI assets and WebSocket telemetry endpoint."""
    event_bus = MissionEventBus()
    config = AuraCodeConfig()
    router = _SequentialLoopRouter(["ok"])
    engine = AuraCodeEngine(config, router, event_bus=event_bus)

    app = create_app(engine)
    client = await aiohttp_client(app)

    # UI Static pages
    res = await client.get("/ui")
    assert res.status == 200
    html = await res.text()
    assert "AURACODE" in html
    assert "MISSION COMMAND" in html
    assert "deck-navigation" in html

    css_res = await client.get("/ui/styles.css")
    assert css_res.status == 200
    assert "--bg-deep" in await css_res.text()

    js_res = await client.get("/ui/app.js")
    assert js_res.status == 200
    assert "connectWebSocket" in await js_res.text()

    # WebSocket connection
    ws = await client.ws_connect("/api/events")
    event_bus.broadcast("agent.step_started", {"request_id": "test_ws", "attempt": 1})
    msg = await asyncio.wait_for(ws.receive_str(), timeout=2.0)
    assert "agent.step_started" in msg
    await ws.close()
