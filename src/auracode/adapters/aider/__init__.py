"""Aider file-system diffing adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry


def register(registry: AdapterRegistry) -> None:
    """Instantiate and register the Aider adapter."""
    from auracode.adapters.aider.adapter import AiderAdapter

    registry.register(AiderAdapter())
