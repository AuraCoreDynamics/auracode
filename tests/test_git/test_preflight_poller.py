"""Unit tests for GitMirrorPoller pre-flight verification gates."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

from auracode.git.mirror_service import GitMirrorService
from auracode.git.poller import GitMirrorPoller
from auracode.grid.lifecycle_client import LifecycleManagementClient


def test_poller_preflight_blocks_restart_on_failure(tmp_path: Path) -> None:
    """Verify that a failing pre-flight command prevents application restart."""
    storage = tmp_path / "mirrors"
    storage.mkdir()
    repo_dir = storage / "testapp.git"
    repo_dir.mkdir()

    mirror_mock = MagicMock(spec=GitMirrorService)
    mirror_mock.storage_path = storage
    # Mock git operations
    mirror_mock._run_git.return_value = "dummy_output"

    lifecycle_mock = MagicMock(spec=LifecycleManagementClient)

    # Command exits 1 (fails)
    poller = GitMirrorPoller(
        mirror_service=mirror_mock,
        lifecycle_client=lifecycle_mock,
        preflight_command=f'"{sys.executable}" -c "import sys; sys.exit(1)"',
    )
    poller._last_hashes["testapp.git"] = "old_hash_123"

    # Mock _get_branch_hash returning new hash
    poller._get_branch_hash = MagicMock(return_value="new_hash_456")  # type: ignore

    poller._check_repos()

    # Lifecycle restart must NOT be called
    lifecycle_mock.trigger_restart.assert_not_called()
    assert poller._last_hashes["testapp.git"] == "new_hash_456"


def test_poller_preflight_permits_restart_on_success(tmp_path: Path) -> None:
    """Verify that a passing pre-flight command permits application restart."""
    storage = tmp_path / "mirrors"
    storage.mkdir()
    repo_dir = storage / "my-service.git"
    repo_dir.mkdir()

    mirror_mock = MagicMock(spec=GitMirrorService)
    mirror_mock.storage_path = storage
    mirror_mock._run_git.return_value = "dummy"

    lifecycle_mock = MagicMock(spec=LifecycleManagementClient)

    # Command exits 0 (passes)
    poller = GitMirrorPoller(
        mirror_service=mirror_mock,
        lifecycle_client=lifecycle_mock,
        preflight_command=f'"{sys.executable}" -c "import sys; sys.exit(0)"',
    )
    poller._last_hashes["my-service.git"] = "hash_v1"
    poller._get_branch_hash = MagicMock(return_value="hash_v2")  # type: ignore

    poller._check_repos()

    # Lifecycle restart MUST be called
    lifecycle_mock.trigger_restart.assert_called_once_with(app_id="my-service")
    assert poller._last_hashes["my-service.git"] == "hash_v2"
