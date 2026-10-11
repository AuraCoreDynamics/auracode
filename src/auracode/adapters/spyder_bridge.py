"""Spyder and Scientific Python IDE bridge for AuraCode."""

from __future__ import annotations

import logging
import subprocess
import webbrowser
from pathlib import Path

from auracode.engine.repo_map import RepoMapBuilder

logger = logging.getLogger(__name__)


class SpyderAuraCodeBridge:
    """Lightweight companion for the Spyder interactive console and scientific workflows."""

    def __init__(self, workspace_root: Path | str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()

    def launch_ui(self, host: str = "127.0.0.1", port: int = 8741) -> str:
        """Open the Mission Command operations deck in the default web browser."""
        url = f"http://{host}:{port}/ui"
        webbrowser.open(url)
        return f"Mission Command opened at: {url}"

    def get_repo_map(self, max_chars: int = 2048) -> str:
        """Inspect the structural AST architecture of the active project (<2KB)."""
        builder = RepoMapBuilder(root_dir=self.workspace_root, max_chars=max_chars)
        return builder.build()

    def verify(
        self,
        command: str = "pytest",
        timeout: int = 60,
    ) -> dict[str, int | str | bool]:
        """Run an interactive verification test suite and capture outcome."""
        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=str(self.workspace_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "passed": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
        except Exception as exc:
            return {
                "passed": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Verification error: {exc}",
            }
