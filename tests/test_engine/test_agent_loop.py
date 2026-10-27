"""Unit tests for the autonomous self-healing agent execution loop."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from auracode.engine.agent_loop import AgenticExecutionLoop
from auracode.engine.core import AuraCodeEngine
from auracode.models.config import AgentPermissions, AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, RequestIntent
from auracode.models.verification import (
    RemediationBudget,
    VerificationCommand,
)
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult
from auracode.utils.journal import FileJournal


class DynamicMockBackend(BaseRouterBackend):
    """Mock backend that can return sequential responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.received_prompts: list[str] = []

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        self.received_prompts.append(prompt)
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
        else:
            resp = self.responses[-1] if self.responses else "ok"
        self.call_count += 1
        return RouteResult(content=resp, model_used="test-model")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_agent_loop_success_in_one_turn(tmp_path: Path) -> None:
    """Verify that a passing verification completes in 1 turn."""
    config = AuraCodeConfig(
        permissions=AgentPermissions(allow_file_write=True, allow_shell_commands=True)
    )
    backend = DynamicMockBackend(["test output"])
    engine = AuraCodeEngine(config, backend)
    loop = AgenticExecutionLoop(engine)

    cmd = f'"{sys.executable}" -c "exit(0)"'
    verif = VerificationCommand(command=cmd, working_directory=str(tmp_path))
    req = EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=RequestIntent.GENERATE_CODE,
        prompt="hello",
        adapter_name="opencode",
    )

    result = await loop.run(req, verification=verif)
    assert result.status == "success"
    assert len(result.remediations) == 1
    assert result.remediations[0].verification.passed is True
    assert backend.call_count == 1


@pytest.mark.asyncio
async def test_agent_loop_remediation_retries(tmp_path: Path) -> None:
    """Verify that failing verification triggers remediation retry."""
    config = AuraCodeConfig(
        permissions=AgentPermissions(allow_file_write=True, allow_shell_commands=True)
    )
    backend = DynamicMockBackend(["turn 1 output", "turn 2 output"])
    engine = AuraCodeEngine(config, backend)
    loop = AgenticExecutionLoop(engine)

    # First attempt fails, second attempt succeeds via temporary file indicator
    flag_file = tmp_path / "flag.txt"
    cmd = (
        f'"{sys.executable}" -c "import os, sys; '
        f"has_f = os.path.exists(r'{flag_file}'); "
        f"open(r'{flag_file}', 'w').close(); "
        f'sys.exit(0 if has_f else 1)"'
    )
    verif = VerificationCommand(command=cmd, working_directory=str(tmp_path))
    req = EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=RequestIntent.GENERATE_CODE,
        prompt="initial prompt",
        adapter_name="opencode",
    )

    result = await loop.run(req, verification=verif)
    assert result.status == "success"
    assert len(result.remediations) == 2
    assert result.remediations[0].verification.passed is False
    assert result.remediations[1].verification.passed is True
    assert backend.call_count == 2
    assert "The previous implementation failed" in backend.received_prompts[1]


@pytest.mark.asyncio
async def test_agent_loop_exhausts_budget(tmp_path: Path) -> None:
    """Verify that consecutive failures halt at max budget."""
    config = AuraCodeConfig(
        permissions=AgentPermissions(allow_file_write=True, allow_shell_commands=True)
    )
    backend = DynamicMockBackend(["always fail"])
    engine = AuraCodeEngine(config, backend)
    loop = AgenticExecutionLoop(engine)

    cmd = f'"{sys.executable}" -c "import sys; sys.stderr.write(\'err\'); sys.exit(1)"'
    verif = VerificationCommand(command=cmd, working_directory=str(tmp_path))
    budget = RemediationBudget(max_attempts=3, current_attempt=0)
    req = EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=RequestIntent.GENERATE_CODE,
        prompt="start",
        adapter_name="opencode",
    )

    result = await loop.run(req, verification=verif, budget=budget)
    assert result.status == "remediation_exhausted"
    assert len(result.remediations) == 3
    assert all(not r.verification.passed for r in result.remediations)


@pytest.mark.asyncio
async def test_agent_loop_permission_denied() -> None:
    """Verify that disallowed shell command returns permission_denied."""
    config = AuraCodeConfig(permissions=AgentPermissions(allow_shell_commands=False))
    backend = DynamicMockBackend(["code"])
    engine = AuraCodeEngine(config, backend)
    loop = AgenticExecutionLoop(engine)

    verif = VerificationCommand(command="echo test")
    req = EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=RequestIntent.GENERATE_CODE,
        prompt="start",
        adapter_name="opencode",
    )
    result = await loop.run(req, verification=verif)
    assert result.status == "permission_denied"
    assert result.rollback_available is True


@pytest.mark.asyncio
async def test_journal_rollback(tmp_path: Path) -> None:
    """Verify that rollback_snapshot restores previous file state."""
    test_file = tmp_path / "hello.py"
    test_file.write_text("print('version 1')", encoding="utf-8")

    journal = FileJournal()
    snap_id = journal.create_snapshot("test_checkpoint")

    # Modify file
    journal.record(
        str(test_file),
        action="write",
        before_content="print('version 1')",
        after_content="print('version 2')",
    )
    test_file.write_text("print('version 2')", encoding="utf-8")

    # Create new file
    new_file = tmp_path / "new.py"
    new_file.write_text("new content", encoding="utf-8")
    journal.record(
        str(new_file),
        action="write",
        before_content=None,
        after_content="new content",
    )

    # Roll back
    reverted = journal.rollback_snapshot(snap_id)
    assert str(test_file) in reverted
    assert str(new_file) in reverted
    assert test_file.read_text(encoding="utf-8") == "print('version 1')"
    assert not new_file.exists()


@pytest.mark.asyncio
async def test_agent_loop_artifact_application(tmp_path: Path) -> None:
    """Verify structured artifact parsing, writing, and journaling."""
    target_file = tmp_path / "calc.py"
    payload = {
        "modifications": [
            {
                "file_path": "calc.py",
                "modification_type": "full_rewrite",
                "content": "def add(a, b):\n    return a + b\n",
                "language": "python",
            }
        ]
    }
    raw_response = f"```json\n{json.dumps(payload)}\n```"

    config = AuraCodeConfig(
        permissions=AgentPermissions(allow_file_write=True, allow_shell_commands=True)
    )
    backend = DynamicMockBackend([raw_response])
    engine = AuraCodeEngine(config, backend)
    loop = AgenticExecutionLoop(engine)

    session = SessionContext(
        session_id="test_session",
        working_directory=str(tmp_path),
    )
    cmd = (
        f'"{sys.executable}" -c "'
        f"import sys; "
        f"sys.path.insert(0, r'{tmp_path}'); "
        f"import calc; "
        f'assert calc.add(2, 3) == 5"'
    )
    verif = VerificationCommand(command=cmd, working_directory=str(tmp_path))
    req = EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=RequestIntent.GENERATE_CODE,
        prompt="write calc.py",
        context=session,
        adapter_name="opencode",
    )

    result = await loop.run(req, verification=verif)
    assert result.status == "success"
    assert target_file.is_file()
    assert "def add(a, b):" in target_file.read_text(encoding="utf-8")
    assert len(loop.journal.entries) >= 1
