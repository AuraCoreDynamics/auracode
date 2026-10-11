"""File history journaling with SHA256 snapshots and transactional rollback."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("AuraCode.Journal")


def get_sha256(content: str) -> str:
    """Calculate SHA256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


class FileJournal:
    """Tracks file modifications with before/after snapshots and transactional rollback."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.snapshots: dict[str, dict[str, Any]] = {}

    def record(
        self,
        path: str,
        action: str,
        before_content: str | None = None,
        after_content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a file modification.

        Args:
            path: Relative or absolute file path.
            action: Action name (e.g., 'write', 'edit', 'delete').
            before_content: Content before change.
            after_content: Content after change.
            metadata: Additional info.

        Returns:
            The created journal entry.
        """
        before_sha = get_sha256(before_content) if before_content is not None else None
        after_sha = get_sha256(after_content) if after_content is not None else None

        entry = {
            "path": path,
            "action": action,
            "before_content": before_content,
            "after_content": after_content,
            "before_sha256": before_sha,
            "after_sha256": after_sha,
            "before_size": len(before_content) if before_content is not None else 0,
            "after_size": len(after_content) if after_content is not None else 0,
            "metadata": metadata or {},
        }
        self.entries.append(entry)
        return entry

    def create_snapshot(self, tag: str = "") -> str:
        """Create a tagged snapshot checkpoint for atomic rollback.

        Returns:
            A unique snapshot identifier string.
        """
        snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        self.snapshots[snapshot_id] = {
            "id": snapshot_id,
            "tag": tag,
            "entry_index": len(self.entries),
            "timestamp": time.time(),
        }
        return snapshot_id

    def rollback_snapshot(self, snapshot_id: str) -> list[str]:
        """Roll back all filesystem modifications recorded after the snapshot.

        Restores each modified file to its before_content, or deletes files created
        after the snapshot point.

        Args:
            snapshot_id: Identifier returned by create_snapshot.

        Returns:
            List of restored or deleted file paths.

        Raises:
            KeyError: If snapshot_id is not found.
        """
        if snapshot_id not in self.snapshots:
            raise KeyError(f"Snapshot ID not found: {snapshot_id}")

        checkpoint = self.snapshots[snapshot_id]
        start_idx = checkpoint["entry_index"]
        entries_to_revert = self.entries[start_idx:]

        rolled_back_paths: set[str] = set()

        # Revert in reverse order of application
        for entry in reversed(entries_to_revert):
            p = Path(entry["path"])
            before = entry.get("before_content")
            if before is not None:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(before, encoding="utf-8")
            else:
                if p.exists():
                    p.unlink()
            rolled_back_paths.add(str(p))

        # Truncate journal entries back to the checkpoint
        self.entries = self.entries[:start_idx]
        del self.snapshots[snapshot_id]

        return sorted(rolled_back_paths)

    def to_dict(self) -> list[dict[str, Any]]:
        """Return all entries as a list of dicts."""
        return list(self.entries)
