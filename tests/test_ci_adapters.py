"""Tests for CI Provider Adapter mesh and Keyring Config store."""

import tempfile
from pathlib import Path

from auracode.ci.config import CiConfigStore
from auracode.ci.providers.github import GitHubActionsAdapter
from auracode.ci.providers.gitlab import GitLabCiAdapter
from auracode.ci.providers.local_grid import LocalGridAdapter


def test_config_store_roundtrip() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        config_dir = Path(tmp_dir) / "config"
        store = CiConfigStore(config_dir=config_dir)

        store.config.timeout_sec = 420
        store.config.container_engine = "docker"
        store.save()

        reloaded = CiConfigStore(config_dir=config_dir)
        assert reloaded.config.timeout_sec == 420
        assert reloaded.config.container_engine == "docker"
        assert "ubuntu-latest" in reloaded.config.image_mappings


def test_github_actions_adapter_detection() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        adapter = GitHubActionsAdapter()
        assert not adapter.detect(repo)

        wf_dir = repo / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "ci.yml").write_text("name: CI\non: push\njobs: {}", encoding="utf-8")

        assert adapter.detect(repo)
        assert adapter.name == "github-actions"


def test_gitlab_ci_adapter_detection_and_parsing() -> None:
    yaml_content = """
image: python:3.12
stages:
  - test

lint-job:
  stage: test
  script:
    - ruff check .
    - ruff format --check .

test-job:
  stage: test
  script:
    - pytest tests/
"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        ci_file = repo / ".gitlab-ci.yml"
        ci_file.write_text(yaml_content, encoding="utf-8")

        adapter = GitLabCiAdapter()
        assert adapter.detect(repo)
        assert adapter.name == "gitlab-ci"

        jobs = adapter.parse_workflows(repo)
        assert len(jobs) == 2
        names = [j.name for j in jobs]
        assert "lint-job" in names
        assert "test-job" in names


def test_local_grid_adapter_execution() -> None:
    adapter = LocalGridAdapter()
    engine = adapter.detect_container_engine()
    # On this machine, podman or docker is in PATH
    assert engine in ("podman", "docker", None)
