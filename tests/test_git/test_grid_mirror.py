"""Unit tests for GridMirrorOrchestrator in git/grid_mirror.py."""

from __future__ import annotations

import subprocess
from pathlib import Path

from auracode.git.grid_mirror import GridMirrorOrchestrator


def test_init_grid_mirror_and_info(tmp_path: Path) -> None:
    grid_storage = tmp_path / "shared_mirrors"
    mirror_path = GridMirrorOrchestrator.init_grid_mirror("my_service", grid_storage)

    assert mirror_path.is_dir()
    assert mirror_path.name == "my_service.git"
    assert (mirror_path / "HEAD").exists()

    info = GridMirrorOrchestrator.get_mirror_info(mirror_path)
    assert info["exists"] is True
    assert info["is_bare"] is True

    # Re-calling returns existing
    mirror_path_2 = GridMirrorOrchestrator.init_grid_mirror("my_service", grid_storage)
    assert mirror_path_2 == mirror_path


def test_sync_mirror_to_node_clone_and_fetch(tmp_path: Path) -> None:
    grid_storage = tmp_path / "storage"
    mirror_path = GridMirrorOrchestrator.init_grid_mirror("app_sync", grid_storage)

    # Initialize a dummy commit in a staging repo and push to the bare mirror
    staging = tmp_path / "staging"
    staging.mkdir()
    subprocess.run(["git", "init"], cwd=str(staging), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=str(staging),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@aura.local"],
        cwd=str(staging),
        check=True,
        capture_output=True,
    )
    (staging / "README.md").write_text("# Sync Test", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(staging), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(staging),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=str(staging),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", str(mirror_path)],
        cwd=str(staging),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=str(staging),
        check=True,
        capture_output=True,
    )

    # Now test sync_mirror_to_node: clones to local_target
    local_target = tmp_path / "node_local"
    ok = GridMirrorOrchestrator.sync_mirror_to_node(mirror_path, local_target)
    assert ok is True
    assert (local_target / ".git").is_dir()
    assert (local_target / "README.md").exists()

    # Calling sync again fetches updates
    ok_repeat = GridMirrorOrchestrator.sync_mirror_to_node(mirror_path, local_target)
    assert ok_repeat is True


def test_get_mirror_info_nonexistent(tmp_path: Path) -> None:
    info = GridMirrorOrchestrator.get_mirror_info(tmp_path / "not_there.git")
    assert info["exists"] is False
