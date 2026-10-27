"""In-memory live IDE state store for active buffer, diagnostics, and open editors.

Enables near-zero latency self-healing and bidirectional MCP tools by caching
diagnostics and editor buffers pushed by IDE shims (VS Code, Visual Studio, Spyder).
"""

from __future__ import annotations

import logging
from typing import Any

from auracode.shim.ide_protocol import Diagnostic, FileSnapshot, IdeContext, TextSelection

logger = logging.getLogger(__name__)


class IdeStateStore:
    """Thread-safe and async-safe in-memory store for active IDE editor state."""

    def __init__(self) -> None:
        self.workspace_root: str = "."
        self.active_file: str | None = None
        self._buffers: dict[str, FileSnapshot] = {}
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._last_active_buffer: dict[str, Any] | None = None

    def update_from_context(self, context: IdeContext) -> None:
        """Update state store from an incoming IdeContext payload."""
        if context.workspace_root:
            self.workspace_root = context.workspace_root
        if context.active_file:
            self.active_file = context.active_file

        for snap in context.open_files:
            self._buffers[snap.path] = snap
            if snap.diagnostics:
                self._diagnostics[snap.path] = list(snap.diagnostics)
            if self.active_file == snap.path:
                self._last_active_buffer = {
                    "path": snap.path,
                    "content": snap.content,
                    "language": snap.language,
                    "selection": snap.selection.model_dump() if snap.selection else None,
                }

    def update_diagnostics(self, file_path: str, diagnostics: list[Diagnostic]) -> None:
        """Update diagnostics for a specific file."""
        self._diagnostics[file_path] = list(diagnostics)
        if file_path in self._buffers:
            old = self._buffers[file_path]
            self._buffers[file_path] = FileSnapshot(
                path=old.path,
                content=old.content,
                language=old.language,
                version=old.version + 1,
                selection=old.selection,
                diagnostics=list(diagnostics),
            )

    def update_buffer(
        self,
        file_path: str,
        content: str,
        language: str | None = None,
        selection: TextSelection | None = None,
    ) -> None:
        """Update in-memory content and cursor selection for an editor buffer."""
        self.active_file = file_path
        existing_diags = self._diagnostics.get(file_path, [])
        snap = FileSnapshot(
            path=file_path,
            content=content,
            language=language,
            selection=selection,
            diagnostics=existing_diags,
        )
        self._buffers[file_path] = snap
        self._last_active_buffer = {
            "path": file_path,
            "content": content,
            "language": language,
            "selection": selection.model_dump() if selection else None,
        }

    def get_diagnostics(
        self,
        file_path: str | None = None,
        severity: str | None = None,
    ) -> list[Diagnostic]:
        """Retrieve diagnostics matching optional file path and severity filter."""
        results: list[Diagnostic] = []
        if file_path:
            norm = file_path.replace("\\", "/")
            for path, diags in self._diagnostics.items():
                if path.replace("\\", "/") == norm or path.endswith(norm):
                    results.extend(diags)
        else:
            for diags in self._diagnostics.values():
                results.extend(diags)

        if severity:
            sev_lower = severity.lower()
            results = [d for d in results if d.severity.lower() == sev_lower]

        return results

    def has_errors(self, file_path: str | None = None) -> bool:
        """Check if any error-level diagnostics exist."""
        errors = self.get_diagnostics(file_path=file_path, severity="error")
        return len(errors) > 0

    def get_active_buffer(self) -> dict[str, Any] | None:
        """Return the current active file buffer, or None if no file is open."""
        if self._last_active_buffer:
            return self._last_active_buffer
        if self.active_file and self.active_file in self._buffers:
            b = self._buffers[self.active_file]
            return {
                "path": b.path,
                "content": b.content,
                "language": b.language,
                "selection": b.selection.model_dump() if b.selection else None,
            }
        return None

    def get_open_buffers(self) -> list[dict[str, Any]]:
        """Return summaries of all open buffers."""
        return [
            {
                "path": b.path,
                "language": b.language,
                "length": len(b.content) if b.content else 0,
                "diagnostic_count": len(b.diagnostics),
            }
            for b in self._buffers.values()
        ]

    def clear(self) -> None:
        """Reset state."""
        self.active_file = None
        self._buffers.clear()
        self._diagnostics.clear()
        self._last_active_buffer = None


# Global singleton instance for the shim process
ide_state = IdeStateStore()
