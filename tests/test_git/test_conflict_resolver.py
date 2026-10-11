"""Unit tests for Git 3-way conflict parser and AI-driven resolver."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from auracode.engine.core import AuraCodeEngine
from auracode.git.conflict_resolver import (
    ConflictMarkerParser,
    MergeConflictResolver,
)
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult
from auracode.utils.journal import FileJournal


class ConflictMockBackend(BaseRouterBackend):
    """Mock backend returning resolved file content."""

    def __init__(self, resolved_content: str) -> None:
        self.resolved_content = resolved_content

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        return RouteResult(content=self.resolved_content, model_used="mock-coder")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def health_check(self) -> bool:
        return True


def test_conflict_parser_standard_block() -> None:
    """Verify ConflictMarkerParser parses standard 2-way conflict blocks."""
    text = (
        "def compute():\n"
        "<<<<<<< HEAD\n"
        "    return 100\n"
        "=======\n"
        "    return 200\n"
        ">>>>>>> feature-branch\n"
    )
    blocks = ConflictMarkerParser.parse_text(text)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.ours_label == "HEAD"
    assert b.ours_content == "    return 100\n"
    assert b.theirs_label == "feature-branch"
    assert b.theirs_content == "    return 200\n"
    assert b.base_content is None


def test_conflict_parser_diff3_block() -> None:
    """Verify ConflictMarkerParser parses diff3 3-way conflict blocks."""
    text = (
        "def greet():\n"
        "<<<<<<< HEAD\n"
        "    return 'Hello, World!'\n"
        "||||||| base\n"
        "    return 'Hello'\n"
        "=======\n"
        "    return 'Hi, World!'\n"
        ">>>>>>> branch-b\n"
    )
    blocks = ConflictMarkerParser.parse_text(text)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.ours_label == "HEAD"
    assert b.base_content == "    return 'Hello'\n"
    assert b.theirs_label == "branch-b"


def test_find_conflicted_files_in_workspace(tmp_path: Path) -> None:
    """Verify scanning directory discovers files containing conflict markers."""
    clean_f = tmp_path / "clean.py"
    clean_f.write_text("x = 1\n", encoding="utf-8")

    conflict_f = tmp_path / "conflicted.py"
    conflict_f.write_text(
        "<<<<<<< ours\nx = 1\n=======\nx = 2\n>>>>>>> theirs\n",
        encoding="utf-8",
    )

    conflicted = ConflictMarkerParser.find_conflicted_files(str(tmp_path))
    assert len(conflicted) == 1
    assert conflicted[0] == conflict_f.resolve()


@pytest.mark.asyncio
async def test_merge_conflict_resolver_success(tmp_path: Path) -> None:
    """Verify MergeConflictResolver replaces conflict blocks and records journal."""
    target_f = tmp_path / "calc.py"
    target_f.write_text(
        "def add(a, b):\n"
        "<<<<<<< ours\n"
        "    return a + b\n"
        "=======\n"
        "    return (a + b)\n"
        ">>>>>>> theirs\n",
        encoding="utf-8",
    )

    resolved_code = "def add(a, b):\n    return a + b\n"
    backend = ConflictMockBackend(resolved_code)
    engine = AuraCodeEngine(AuraCodeConfig(), backend)
    journal = FileJournal()
    resolver = MergeConflictResolver(engine, journal=journal)

    success, msg = await resolver.resolve_file(target_f)
    assert success is True
    assert "Successfully resolved" in msg
    assert target_f.read_text(encoding="utf-8") == resolved_code
    assert len(journal.entries) == 1
    assert journal.entries[0]["action"] == "resolve_conflict"


@pytest.mark.asyncio
async def test_merge_conflict_resolver_rejects_leftover_markers(tmp_path: Path) -> None:
    """Verify MergeConflictResolver rejects output if conflict markers remain."""
    target_f = tmp_path / "broken.py"
    target_f.write_text(
        "<<<<<<< ours\na = 1\n=======\na = 2\n>>>>>>> theirs\n",
        encoding="utf-8",
    )

    bad_response = "<<<<<<< still broken\na = 3\n>>>>>>>"
    backend = ConflictMockBackend(bad_response)
    engine = AuraCodeEngine(AuraCodeConfig(), backend)
    resolver = MergeConflictResolver(engine)

    success, msg = await resolver.resolve_file(target_f)
    assert success is False
    assert "still contained Git conflict markers" in msg
