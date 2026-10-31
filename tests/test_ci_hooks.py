"""Tests for Git pre-push hook installation, chaining, and bypass handling."""

import json
import tempfile
from pathlib import Path

from auracode.ci.hooks import (
    dispatch_pre_push,
    install_pre_push_hook,
    log_bypass_event,
)


def test_install_pre_push_hook() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        git_dir = repo / ".git"
        git_dir.mkdir(parents=True)

        hook_path = install_pre_push_hook(repo)
        assert hook_path.is_file()

        content = hook_path.read_text(encoding="utf-8")
        assert "AuraCode & AuraGrid Pre-Push Verification Gate" in content
        assert "hook-dispatch" in content
        assert "\r\n" not in content  # Strictly LF line endings


def test_install_pre_push_hook_chains_existing() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)

        existing_hook = hooks_dir / "pre-push"
        existing_hook.write_text("#!/bin/sh\necho 'custom hook'\n", encoding="utf-8")

        install_pre_push_hook(repo)

        # Original hook should be preserved as pre-push.local
        local_hook = hooks_dir / "pre-push.local"
        assert local_hook.is_file()
        assert "custom hook" in local_hook.read_text(encoding="utf-8")

        # Main hook should now dispatch to auracode
        main_content = existing_hook.read_text(encoding="utf-8")
        assert "hook-dispatch" in main_content


def test_dispatch_pre_push_buffers_stdin_for_chained_hook() -> None:
    """A3.1: Verify stdin is buffered and safely forwarded to chained hook (git-lfs style)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = Path(tmp_dir)
        hooks_dir = repo / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)

        # Create a pre-push.local that consumes stdin and records it to consumed.txt
        consumed_file = repo / "consumed.txt"
        local_hook = hooks_dir / "pre-push.local"
        local_hook.write_text(
            "#!/bin/sh\ncat > consumed.txt\n",
            encoding="utf-8",
        )

        stdin_content = (
            "refs/heads/main 1111111111111111111111111111111111111111 "
            "refs/heads/main 0000000000000000000000000000000000000000\n"
        )

        code = dispatch_pre_push(
            stdin_content=stdin_content,
            remote_name="origin",
            remote_url="git@github.com:test/repo.git",
            repo_path=repo,
        )

        assert code == 0
        assert consumed_file.is_file()
        content = consumed_file.read_text(encoding="utf-8")
        assert "1111111111111111111111111111111111111111" in content


def test_log_bypass_event_jsonl() -> None:
    """A3.3: Verify bypass is written to structured JSONL with all audit fields."""
    audit_file = Path.home() / ".auracode" / "audit" / "bypass.jsonl"
    log_bypass_event("/path/to/test-repo", "a" * 40, ref="refs/heads/main", reason="emergency-fix")

    assert audit_file.is_file()
    lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert lines

    last_entry = json.loads(lines[-1])
    assert last_entry["sha"] == "a" * 40
    assert last_entry["ref"] == "refs/heads/main"
    assert last_entry["reason"] == "emergency-fix"
    assert "ts" in last_entry
    assert "hostname" in last_entry
    assert "user" in last_entry
