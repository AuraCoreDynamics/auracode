"""Unit tests for the deterministic zero-vector AST repo-map and AuraXLM hook."""

from __future__ import annotations

from pathlib import Path

from auracode.engine.repo_map import RepoMapBuilder
from auracode.models.request import (
    RetrievalMode,
    RetrievalPolicy,
)
from auracode.routing.auraxlm_hook import AuraXlmRetrievalClient
from auracode.routing.intent_map import build_context_prompt


def test_repo_map_extracts_python_symbols(tmp_path: Path) -> None:
    """Verify that RepoMapBuilder extracts classes and methods from Python files."""
    code_file = tmp_path / "service.py"
    code_file.write_text(
        "class OrderService:\n"
        "    def __init__(self, db):\n"
        "        pass\n\n"
        "    def create_order(self, item_id, qty):\n"
        "        pass\n\n"
        "def helper_fn(x, y):\n"
        "    return x + y\n",
        encoding="utf-8",
    )

    builder = RepoMapBuilder(root_dir=str(tmp_path), max_chars=1024)
    rendered = builder.build()
    file_count, symbol_count = builder.count_symbols()

    assert file_count == 1
    assert symbol_count >= 3
    assert "service.py:" in rendered
    assert "class OrderService" in rendered
    assert "def create_order(item_id, qty)" in rendered
    assert "def helper_fn(x, y)" in rendered


def test_repo_map_respects_max_chars(tmp_path: Path) -> None:
    """Verify that RepoMapBuilder respects the character truncation budget."""
    for i in range(20):
        f = tmp_path / f"module_{i}.py"
        f.write_text(
            f"class LongClassNameForTestingNumber{i}:\n"
            f"    def method_one(self, a, b, c):\n"
            f"        pass\n"
            f"    def method_two(self, x, y, z):\n"
            f"        pass\n",
            encoding="utf-8",
        )

    builder = RepoMapBuilder(root_dir=str(tmp_path), max_chars=400)
    rendered = builder.build()

    assert len(rendered) <= 400
    assert "... [truncated" in rendered or rendered.endswith("...")


def test_repo_map_polyglot_extraction(tmp_path: Path) -> None:
    """Verify regex extraction for non-Python files like C# and TypeScript."""
    cs_file = tmp_path / "App.cs"
    cs_file.write_text(
        "public class OrderProcessor {\n    public void Process() {}\n}\n",
        encoding="utf-8",
    )
    ts_file = tmp_path / "api.ts"
    ts_file.write_text(
        "export interface UserDto {\n    id: string;\n}\n",
        encoding="utf-8",
    )

    builder = RepoMapBuilder(root_dir=str(tmp_path), max_chars=1024)
    rendered = builder.build()

    assert "App.cs:" in rendered
    assert "class OrderProcessor" in rendered
    assert "api.ts:" in rendered
    assert "interface UserDto" in rendered


def test_repo_map_skips_ignored_directories(tmp_path: Path) -> None:
    """Verify that .git and virtual environments are ignored."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "internal.py").write_text("class InternalSecret: pass", encoding="utf-8")

    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "dep.py").write_text("class Dependency: pass", encoding="utf-8")

    src_file = tmp_path / "app.py"
    src_file.write_text("class ValidApp: pass", encoding="utf-8")

    builder = RepoMapBuilder(root_dir=str(tmp_path), max_chars=1024)
    rendered = builder.build()

    assert "InternalSecret" not in rendered
    assert "Dependency" not in rendered
    assert "class ValidApp" in rendered


def test_auraxlm_retrieval_fallback_and_notice() -> None:
    """Verify graceful fallback with DegradationNotice when AuraXLM is not configured."""
    client = AuraXlmRetrievalClient(endpoint=None)
    assert not client.is_available

    policy = RetrievalPolicy(mode=RetrievalMode.REQUIRED)
    repomap_text = "local repo map content"

    effective_text, notices = client.negotiate_retrieval(policy, repomap_text)
    assert effective_text == repomap_text
    assert len(notices) == 1
    assert notices[0].capability == "neural_retrieval"
    assert "AuraXLM semantic retrieval not configured" in notices[0].reason


def test_auraxlm_retrieval_when_configured() -> None:
    """Verify active indicator when AuraXLM endpoint is set."""
    client = AuraXlmRetrievalClient(endpoint="http://grid-node-1:7070")
    assert client.is_available

    policy = RetrievalPolicy(mode=RetrievalMode.AUTO)
    effective_text, notices = client.negotiate_retrieval(policy, "local map")

    assert "AuraXLM Neural Retrieval active" in effective_text
    assert len(notices) == 0


def test_build_context_prompt_with_repo_map() -> None:
    """Verify build_context_prompt injects Architecture Map block."""
    prompt = build_context_prompt(context=None, repo_map="src/core.py: class Engine")
    assert "## Architecture Map" in prompt
    assert "src/core.py: class Engine" in prompt
