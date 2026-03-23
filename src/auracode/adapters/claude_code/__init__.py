"""Claude Code CLI adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry


def register(registry: AdapterRegistry) -> None:
    """Instantiate and register the Claude Code adapter."""
    from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter

    registry.register(ClaudeCodeAdapter())
