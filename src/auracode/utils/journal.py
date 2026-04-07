"""File history journaling with SHA256 snapshots."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger("AuraCode.Journal")


def get_sha256(content: str) -> str:
    """Calculate SHA256 hash of a string."""
    return hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()


class FileJournal:
    """Tracks file modifications with before/after snapshots."""

    def __init__(self):
        self.entries: list[dict[str, Any]] = []

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
            "before_sha256": before_sha,
            "after_sha256": after_sha,
            "before_size": len(before_content) if before_content is not None else 0,
            "after_size": len(after_content) if after_content is not None else 0,
            "metadata": metadata or {},
        }
        self.entries.append(entry)
        return entry

    def to_dict(self) -> list[dict[str, Any]]:
        """Return all entries as a list of dicts."""
        return self.entries
