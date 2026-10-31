"""Git pre-push hook installation, dispatch, and verification integration."""

from __future__ import annotations

import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ZERO_SHA = "0000000000000000000000000000000000000000"


def get_hooks_dir(repo_path: str | Path = ".") -> Path:
    """Discovers git hooks directory respecting core.hooksPath and git worktrees."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            p = Path(res.stdout.strip())
            return p if p.is_absolute() else (Path(repo_path) / p).resolve()
    except Exception:
        pass
    return Path(repo_path).resolve() / ".git" / "hooks"


def log_bypass_event(
    repo_path: str | Path,
    commit_sha: str,
    ref: str = "",
    reason: str = "environment_variable",
) -> None:
    """Logs a bypass event as structured JSONL to ~/.auracode/audit/bypass.jsonl."""
    audit_file = Path.home() / ".auracode" / "audit" / "bypass.jsonl"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "unknown",
        "hostname": platform.node(),
        "repo": str(Path(repo_path).resolve()),
        "ref": ref,
        "sha": commit_sha,
        "reason": reason,
    }
    with audit_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def find_shell() -> str | None:
    """Finds appropriate POSIX shell executable for running git hook scripts."""
    if sys.platform == "win32":
        for candidate in (
            r"C:\Program Files\Git\bin\sh.exe",
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\sh.exe",
        ):
            if Path(candidate).is_file():
                return candidate
        return shutil.which("sh")
    return shutil.which("sh") or shutil.which("bash")


def dispatch_pre_push(
    stdin_content: str,
    remote_name: str = "",
    remote_url: str = "",
    repo_path: str | Path = ".",
) -> int:
    """Dispatches pre-push verification.

    Buffers stdin completely to prevent chained hooks (e.g. git-lfs) from starving verification.
    Replays buffered stdin into pre-push.local if present after verification passes.
    """
    repo = Path(repo_path).resolve()

    # 1. Check for bypass environment flags
    bypass_ag = os.environ.get("AURAGRID_CI_BYPASS") == "1"
    bypass_ac = os.environ.get("AURACODE_CI_BYPASS") == "1"
    is_bypassed = bypass_ag or bypass_ac

    lines = [line.strip() for line in stdin_content.splitlines() if line.strip()]

    if is_bypassed:
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                ref, sha = parts[0], parts[1]
                log_bypass_event(repo, sha, ref, reason="environment_variable")
        sys.stderr.write(
            "[WARN] AuraCode CI: Pre-push verification gate BYPASSED by environment flag.\n"
        )
        return 0

    # 2. Verify all pushing commit SHAs
    shas_to_verify: list[tuple[str, str]] = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 2:
            local_ref, local_sha = parts[0], parts[1]
            if local_sha != ZERO_SHA:
                shas_to_verify.append((local_ref, local_sha))

    if shas_to_verify:
        from auracode.ci.providers.local_grid import LocalGridAdapter

        adapter = LocalGridAdapter()
        jobs = adapter.parse_workflows(repo)

        if jobs:
            for local_ref, sha in shas_to_verify:
                sys.stderr.write(
                    f"[CI] Verifying ref '{local_ref}' ({sha[:8]}) before remote push...\n"
                )
                for job in jobs:
                    sys.stderr.write(f"  [RUN] {job.name}...\n")
                    res = adapter.execute_job_locally(repo, job, commit_sha=sha)
                    if res.exit_code != 0:
                        sys.stderr.write(
                            f"\n[FAIL] AuraCode CI: Verification failed for {job.name} on "
                            f"commit {sha[:8]}.\n"
                        )
                        if res.diagnostic_summary:
                            sys.stderr.write(f"Diagnostic: {res.diagnostic_summary[:300]}\n")
                        sys.stderr.write(
                            "Run 'auracode ci repair' to autonomously fix detected issues.\n"
                        )
                        return 1
                    sys.stderr.write(f"  [PASS] {job.name} ({res.duration_ms}ms)\n")

    sys.stderr.write("[OK] AuraCode CI: Pre-push verification PASSED.\n")

    # 3. Chain pre-push.local if present, replaying buffered stdin
    hooks_dir = get_hooks_dir(repo)
    local_hook = hooks_dir / "pre-push.local"
    if local_hook.is_file():
        sh_bin = find_shell()
        try:
            target_path = local_hook.relative_to(repo).as_posix()
        except ValueError:
            target_path = local_hook.as_posix()

        if sh_bin:
            args = [sh_bin, target_path]
        else:
            args = [str(local_hook)]
        if remote_name:
            args.append(remote_name)
        if remote_url:
            args.append(remote_url)
        proc = subprocess.run(
            args,
            input=stdin_content,
            text=True,
            check=False,
            cwd=str(repo),
            shell=(sys.platform == "win32" and not sh_bin),
        )
        return proc.returncode

    return 0


def install_pre_push_hook(repo_path: str | Path = ".") -> Path:
    """Installs the blocking AuraCode pre-push hook in the specified repository."""
    repo = Path(repo_path).resolve()
    hooks_dir = get_hooks_dir(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    hook_file = hooks_dir / "pre-push"

    # Preserve any existing non-AuraCode hook as pre-push.local
    if hook_file.exists():
        existing_content = hook_file.read_text(encoding="utf-8", errors="ignore")
        if "AuraCode" not in existing_content:
            local_backup = hooks_dir / "pre-push.local"
            idx = 1
            while local_backup.exists():
                local_backup = hooks_dir / f"pre-push.local.{idx}"
                idx += 1
            local_backup.write_text(existing_content, encoding="utf-8")
            try:
                mode = local_backup.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
                local_backup.chmod(mode)
            except Exception:
                pass

    python_bin = sys.executable
    hook_script = f"""#!/bin/sh
# AuraCode & AuraGrid Pre-Push Verification Gate
exec "{python_bin}" -m auracode.ci.cli ci hook-dispatch "$@"
"""
    normalized = hook_script.replace("\r\n", "\n")
    hook_file.write_bytes(normalized.encode("utf-8"))

    try:
        hook_file.chmod(hook_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

    return hook_file
