"""Copilot CLI adapter — stub for future implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from auracode.engine.registry import AdapterRegistry

logger = structlog.get_logger(__name__)


def register(registry: AdapterRegistry) -> None:
    """Copilot adapter is not yet implemented."""
    logger.warning("adapter_not_implemented", adapter="copilot")
