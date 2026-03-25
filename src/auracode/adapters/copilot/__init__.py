"""Copilot CLI adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry


def register(registry: AdapterRegistry) -> None:
    """Instantiate and register the Copilot adapter."""
    from auracode.adapters.copilot.adapter import CopilotAdapter

    registry.register(CopilotAdapter())
