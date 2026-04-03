"""Application configuration model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AuraCodeConfig(BaseModel):
    """Top-level configuration for the AuraCode engine."""

    router_config_path: str | None = None
    default_adapter: str = "opencode"
    log_level: str = "INFO"
    grid_endpoint: str | None = None
    grid_failover_to_local: bool = True
    local_context_limit: int = 100_000
    adapters: dict[str, dict[str, Any]] = {}
    # Grid TLS/PKI (TG4)
    grid_tls_cert: str | None = None
    grid_tls_key: str | None = None
    grid_ca_cert: str | None = None
    grid_server_name: str | None = None
    grid_default_routing: str = "auto"
    # Sovereignty/retrieval defaults (TG7)
    default_sovereignty_enforcement: str = "none"
    default_sensitivity_label: str | None = None
    default_retrieval_mode: str = "disabled"
    default_execution_mode: str = "standard"
