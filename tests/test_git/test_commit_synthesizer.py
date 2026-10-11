"""Unit tests for the Conventional Commit synthesizer."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from auracode.engine.core import AuraCodeEngine
from auracode.git.commit_synthesizer import CommitSynthesizer
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult


class CommitMockBackend(BaseRouterBackend):
    """Mock backend returning conventional commit message."""

    def __init__(self, message: str) -> None:
        self.message = message

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        return RouteResult(content=self.message, model_used="mock-coder")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def health_check(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_commit_synthesizer_empty_diff() -> None:
    """Verify handling when git diff --staged is empty."""
    backend = CommitMockBackend("feat: dummy")
    engine = AuraCodeEngine(AuraCodeConfig(), backend)
    synthesizer = CommitSynthesizer(engine)

    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = ""
        mock_run.return_value.returncode = 0
        msg = await synthesizer.generate_commit_message()
        assert "Empty diff" in msg


@pytest.mark.asyncio
async def test_commit_synthesizer_generates_message() -> None:
    """Verify commit message generation when staged diff exists."""
    expected_msg = "feat(auth): add multi-factor authentication support"
    backend = CommitMockBackend(f"```\n{expected_msg}\n```")
    engine = AuraCodeEngine(AuraCodeConfig(), backend)
    synthesizer = CommitSynthesizer(engine)

    fake_diff = "+def enable_mfa(): pass\n"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.stdout = fake_diff
        mock_run.return_value.returncode = 0
        msg = await synthesizer.generate_commit_message()
        assert msg == expected_msg
