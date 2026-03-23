"""OpenAI shim adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry


def register(registry: AdapterRegistry) -> None:
    """Instantiate and register the OpenAI shim adapter."""
    from auracode.adapters.openai_shim.adapter import OpenAIShimAdapter

    registry.register(OpenAIShimAdapter())
