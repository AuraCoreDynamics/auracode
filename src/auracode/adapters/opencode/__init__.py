"""OpenCode adapter package — AuraCode-native adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry


def register(registry: AdapterRegistry) -> None:
    """Instantiate and register the OpenCode adapter."""
    from auracode.adapters.opencode.adapter import OpenCodeAdapter

    registry.register(OpenCodeAdapter())
