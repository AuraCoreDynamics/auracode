"""Multi-workspace fleet manager for architect mission command."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from auracode.git.conflict_resolver import ConflictMarkerParser

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACES_FILE = Path.home() / ".auracode" / "workspaces.json"


class FleetWorkspaceManager:
    """Manages and monitors multiple registered project workspaces."""

    def __init__(self, persistence_file: Path | str | None = None) -> None:
        self.persistence_file = (
            Path(persistence_file).resolve() if persistence_file else DEFAULT_WORKSPACES_FILE
        )
        self._workspaces: set[str] = set()
        self._load()

    def _load(self) -> None:
        """Load registered workspaces from persistence file."""
        if self.persistence_file.is_file():
            try:
                data = json.loads(self.persistence_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        p = Path(item).resolve()
                        if p.is_dir():
                            self._workspaces.add(str(p))
            except Exception as exc:
                logger.warning("Failed to load workspaces from %s: %s", self.persistence_file, exc)

        # Ensure current workspace is registered if list is empty
        if not self._workspaces:
            self._workspaces.add(str(Path(".").resolve()))

    def _save(self) -> None:
        """Persist registered workspace paths to JSON file."""
        try:
            self.persistence_file.parent.mkdir(parents=True, exist_ok=True)
            self.persistence_file.write_text(
                json.dumps(sorted(list(self._workspaces)), indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to save workspaces to %s: %s", self.persistence_file, exc)

    def register(self, path: Path | str) -> dict[str, Any]:
        """Register a new workspace path."""
        p = Path(path).resolve()
        if not p.is_dir():
            raise ValueError(f"Path does not exist or is not a directory: {p}")
        path_str = str(p)
        self._workspaces.add(path_str)
        self._save()
        return self._scan_workspace_sync(p)

    def unregister(self, path: Path | str) -> bool:
        """Unregister a workspace path."""
        p = Path(path).resolve()
        path_str = str(p)
        if path_str in self._workspaces:
            self._workspaces.remove(path_str)
            # Keep at least current directory registered
            if not self._workspaces:
                self._workspaces.add(str(Path(".").resolve()))
            self._save()
            return True
        return False

    def list_paths(self) -> list[str]:
        """Return raw list of registered workspace paths."""
        return sorted(list(self._workspaces))

    def _scan_workspace_sync(self, root_p: Path) -> dict[str, Any]:
        """Synchronously scan a workspace for Git metadata and conflict status."""
        branch = "unknown"
        is_dirty = False

        if (root_p / ".git").exists():
            try:
                res = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=str(root_p),
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if res.returncode == 0 and res.stdout.strip():
                    branch = res.stdout.strip()

                st_res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(root_p),
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if st_res.returncode == 0 and st_res.stdout.strip():
                    is_dirty = True
            except Exception as exc:
                logger.debug("Git scan error in %s: %s", root_p, exc)

        conflicts = ConflictMarkerParser.find_conflicted_files(str(root_p))

        return {
            "name": root_p.name,
            "path": str(root_p),
            "branch": branch,
            "dirty": is_dirty,
            "conflict_count": len(conflicts),
            "status": "active" if root_p.is_dir() else "missing",
        }

    async def scan_workspace(self, root_p: Path) -> dict[str, Any]:
        """Asynchronously scan a workspace off the main event loop."""
        return await asyncio.to_thread(self._scan_workspace_sync, root_p)

    async def list_workspaces(self) -> list[dict[str, Any]]:
        """Scan and return status for all registered workspaces."""
        results = []
        for path_str in sorted(list(self._workspaces)):
            p = Path(path_str)
            info = await self.scan_workspace(p)
            results.append(info)
        return results
