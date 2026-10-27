"""Polls bare/mirror repositories to detect pushes and trigger app restarts."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from ..grid.lifecycle_client import LifecycleManagementClient
from .mirror_service import GitMirrorService

logger = logging.getLogger(__name__)


class GitMirrorPoller:
    """Polls bare/mirror repositories to detect pushes to monitored branches.

    When a change is detected, runs optional pre-flight verification gates before
    triggering an app restart via LifecycleManagementClient.
    """

    def __init__(
        self,
        mirror_service: GitMirrorService,
        lifecycle_client: LifecycleManagementClient,
        preflight_command: str | None = None,
        preflight_timeout: int = 120,
        event_bus: Any | None = None,
        mas_client: Any | None = None,
    ) -> None:
        self.mirror_service = mirror_service
        self.lifecycle_client = lifecycle_client
        self.preflight_command = preflight_command or os.environ.get(
            "AURACODE_GIT_PREFLIGHT_COMMAND"
        )
        self.preflight_timeout = preflight_timeout
        self.event_bus = event_bus
        self.mas_client = mas_client
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_hashes: dict[str, str] = {}

        self.repo_mapping = self._load_mapping()
        self.poll_interval_seconds = int(os.environ.get("AURACODE_GIT_POLL_INTERVAL", "15"))
        self.monitored_branch = os.environ.get("AURACODE_GIT_POLL_BRANCH", "main")

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.event_bus:
            try:
                self.event_bus.broadcast(event_type, payload)
            except Exception as exc:
                logger.debug(f"Failed to broadcast event: {exc}")

    def _load_mapping(self) -> dict[str, str]:
        mapping_file = os.environ.get("AURACODE_REPO_MAPPING_FILE")
        if mapping_file and Path(mapping_file).exists():
            try:
                with open(mapping_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load repo mapping from {mapping_file}: {e}")
        return {}

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Poller is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="GitMirrorPoller")
        self._thread.start()
        logger.info(
            f"Started GitMirrorPoller (interval={self.poll_interval_seconds}s, "
            f"branch={self.monitored_branch})"
        )

    def stop(self) -> None:
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join(timeout=5)
            self._thread = None
            logger.info("Stopped GitMirrorPoller")

    def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._check_repos()
            except Exception as e:
                logger.error(f"Error during git polling: {e}")

            self._stop_event.wait(self.poll_interval_seconds)

    def _check_repos(self) -> None:
        storage_path = self.mirror_service.storage_path
        if not storage_path.exists():
            return

        for repo_dir in storage_path.iterdir():
            if not repo_dir.is_dir() or not repo_dir.name.endswith(".git"):
                continue

            repo_name = repo_dir.name
            app_id = self.repo_mapping.get(repo_name) or self.repo_mapping.get(
                repo_name.replace(".git", "")
            )

            if not app_id:
                app_id = repo_name.replace(".git", "")

            current_hash = self._get_branch_hash(repo_dir, self.monitored_branch)
            if not current_hash:
                continue

            last_hash = self._last_hashes.get(repo_name)
            if last_hash and current_hash != last_hash:
                logger.info(f"Detected push to {repo_name} on branch {self.monitored_branch}.")
                self._emit(
                    "git.mirror_polled",
                    {
                        "repo": repo_name,
                        "branch": self.monitored_branch,
                        "commit": current_hash,
                        "app_id": app_id,
                    },
                )
                if self.preflight_command:
                    passed = self._run_preflight(repo_dir, current_hash, app_id)
                    if not passed:
                        self._last_hashes[repo_name] = current_hash
                        continue

                logger.info(f"Triggering restart for app {app_id}.")
                self.lifecycle_client.trigger_restart(app_id=app_id)

            self._last_hashes[repo_name] = current_hash

    def _run_preflight(self, repo_dir: Path, commit_hash: str, app_id: str) -> bool:
        """Run pre-flight verification command against a clean checkout of the commit."""
        scratch_dir = Path(tempfile.mkdtemp(prefix=f"preflight_{app_id}_"))
        start_time = time.time()
        try:
            self.mirror_service._run_git(
                ["clone", str(repo_dir), str(scratch_dir)],
                cwd=self.mirror_service.storage_path,
            )
            self.mirror_service._run_git(["checkout", commit_hash], cwd=scratch_dir)

            logger.info(
                f"Running pre-flight `{self.preflight_command}` for {app_id} at {commit_hash}"
            )
            proc = subprocess.run(
                self.preflight_command,
                shell=True,
                stdin=subprocess.DEVNULL,
                cwd=scratch_dir,
                capture_output=True,
                text=True,
                timeout=self.preflight_timeout,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            if proc.returncode != 0:
                logger.error(
                    f"Pre-flight verification failed for {app_id} at {commit_hash} "
                    f"(exit {proc.returncode}, {duration_ms}ms). Restart aborted."
                )
                self._record_preflight_error(app_id, commit_hash, proc.stdout, proc.stderr)
                self._emit(
                    "git.preflight_result",
                    {
                        "app_id": app_id,
                        "commit": commit_hash,
                        "passed": False,
                        "returncode": proc.returncode,
                        "duration_ms": duration_ms,
                    },
                )
                return False

            logger.info(
                f"Pre-flight verification passed for {app_id} at {commit_hash} ({duration_ms}ms)."
            )
            self._emit(
                "git.preflight_result",
                {
                    "app_id": app_id,
                    "commit": commit_hash,
                    "passed": True,
                    "returncode": 0,
                    "duration_ms": duration_ms,
                },
            )
            return True
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Pre-flight execution error for {app_id}: {exc}")
            self._record_preflight_error(app_id, commit_hash, "", str(exc))
            self._emit(
                "git.preflight_result",
                {
                    "app_id": app_id,
                    "commit": commit_hash,
                    "passed": False,
                    "returncode": -1,
                    "duration_ms": duration_ms,
                },
            )
            return False
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)

    def _record_preflight_error(
        self, app_id: str, commit_hash: str, stdout: str, stderr: str
    ) -> None:
        log_dir = Path("app_data/auracode")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "poller_errors.log"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(
                f"\n--- [{app_id}] Commit {commit_hash} FAILED ---\n"
                f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}\n"
            )

    def _get_branch_hash(self, repo_path: Path, branch: str) -> str | None:
        try:
            output = self.mirror_service._run_git(
                ["show-ref", f"refs/heads/{branch}"], cwd=repo_path
            )
            if output:
                return output.split()[0]
        except Exception:
            pass
        return None
