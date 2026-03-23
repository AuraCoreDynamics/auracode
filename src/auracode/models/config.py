"""Application configuration model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuraCodeConfig(BaseModel):
    """Top-level configuration for the AuraCode engine."""

    router_config_path: str | None = None
    default_adapter: str = "claude-code"
    log_level: str = "INFO"
    grid_endpoint: str | None = None
    grid_failover_to_local: bool = True
    local_context_limit: int = 100_000
    adapters: dict[str, dict[str, Any]] = {}
