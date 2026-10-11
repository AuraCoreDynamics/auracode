"""Distributed Git bare-mirror orchestrator for AuraGrid cluster storage."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GridMirrorOrchestrator:
    """Manages distributed Git bare mirrors hosted on AuraGrid shared storage."""

    @classmethod
    def _run_git(cls, args: list[str], cwd: Path | None = None) -> str:
        """Execute a Git CLI command safely."""
        cmd = ["git"] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return res.stdout.strip()
        except subprocess.CalledProcessError as exc:
            logger.error("Git command failed: %s (stderr: %s)", " ".join(cmd), exc.stderr)
            raise RuntimeError(f"Git execution error: {exc.stderr.strip()}") from exc

    @classmethod
    def init_grid_mirror(cls, app_id: str, grid_storage_path: Path | str) -> Path:
        """Initialize a shared bare repository on AuraGrid shared storage."""
        storage = Path(grid_storage_path).resolve()
        storage.mkdir(parents=True, exist_ok=True)

        repo_name = f"{app_id}.git" if not app_id.endswith(".git") else app_id
        mirror_path = storage / repo_name

        if mirror_path.exists():
            logger.info("Grid mirror already exists at %s", mirror_path)
            return mirror_path

        mirror_path.mkdir(parents=True, exist_ok=True)
        cls._run_git(["init", "--bare", "--shared=group"], cwd=mirror_path)
        try:
            cls._run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=mirror_path)
        except Exception:
            pass
        logger.info("Initialized shared grid bare mirror at %s", mirror_path)
        return mirror_path

    @classmethod
    def sync_mirror_to_node(cls, mirror_path: Path | str, local_target: Path | str) -> bool:
        """Clone or sync updates from the grid bare mirror down to a node directory."""
        mirror = Path(mirror_path).resolve()
        target = Path(local_target).resolve()

        if not mirror.is_dir():
            raise ValueError(f"Grid mirror path does not exist: {mirror}")

        if not (target / ".git").is_dir():
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                cls._run_git(["clone", str(mirror), str(target)])
                try:
                    cls._run_git(["checkout"], cwd=target)
                except Exception:
                    pass
                return True
            except Exception as exc:
                logger.error("Failed to clone mirror to node: %s", exc)
                return False

        # Existing working tree: fetch and fast-forward
        try:
            cls._run_git(["fetch", "origin"], cwd=target)
            return True
        except Exception as exc:
            logger.error("Failed to sync node from mirror: %s", exc)
            return False

    @classmethod
    def get_mirror_info(cls, mirror_path: Path | str) -> dict[str, Any]:
        """Query branch and commit metadata for a grid bare mirror."""
        mirror = Path(mirror_path).resolve()
        if not mirror.is_dir():
            return {"exists": False, "path": str(mirror)}

        head_ref = "unknown"
        latest_commit = "none"

        try:
            head_ref = cls._run_git(["symbolic-ref", "--short", "HEAD"], cwd=mirror)
        except Exception:
            pass

        try:
            latest_commit = cls._run_git(["rev-parse", "HEAD"], cwd=mirror)
        except Exception:
            pass

        return {
            "exists": True,
            "path": str(mirror),
            "is_bare": True,
            "head_ref": head_ref,
            "latest_commit": latest_commit,
        }
