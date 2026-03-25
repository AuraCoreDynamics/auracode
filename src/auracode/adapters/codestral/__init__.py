"""Codestral code-completion adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry


def register(registry: AdapterRegistry) -> None:
    """Instantiate and register the Codestral adapter."""
    from auracode.adapters.codestral.adapter import CodestralAdapter

    registry.register(CodestralAdapter())
