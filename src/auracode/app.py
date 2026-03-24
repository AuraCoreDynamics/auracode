"""Application bootstrap — wires config, registries, engine."""

from __future__ import annotations

import os
from typing import Any

import structlog
import yaml

from auracode.adapters.loader import discover_adapters
from auracode.engine.core import AuraCodeEngine
from auracode.engine.preferences import PreferencesManager
from auracode.engine.registry import AdapterRegistry, BackendRegistry
from auracode.models.config import AuraCodeConfig
from auracode.util.logging import configure_logging

log = structlog.get_logger(__name__)


def _safe_configure_logging(level: str) -> None:
    """Call configure_logging, falling back to a minimal structlog setup.

    The standard ``configure_logging`` uses ``add_logger_name`` which is
    incompatible with ``PrintLoggerFactory``.  When that combination causes
    an error we fall back to a minimal config that avoids the conflict.
    """
    try:
        configure_logging(level)
        # Verify the config works by emitting a test event
        structlog.get_logger("_boot").debug("logging_configured")
    except (AttributeError, Exception):
        # Fall back to a minimal working config
        import logging
        import sys

        numeric_level = getattr(logging, level.upper(), logging.INFO)
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.dev.ConsoleRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=False,
        )
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stderr,
            level=numeric_level,
        )


def load_config(config_path: str | None = None) -> AuraCodeConfig:
    """Load config from yaml file or return defaults."""
    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        return AuraCodeConfig(**data)
    # Try default locations
    for path in ["auracode.yaml", os.path.expanduser("~/.auracode.yaml")]:
        if os.path.exists(path):
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            return AuraCodeConfig(**data)
    return AuraCodeConfig()


def create_application(
    config_path: str | None = None,
) -> tuple[AuraCodeEngine, AdapterRegistry, BackendRegistry, PreferencesManager]:
    """Bootstrap the full AuraCode application.

    Returns a tuple of ``(engine, adapter_registry, backend_registry, preferences_manager)``.
    """
    config = load_config(config_path)
    _safe_configure_logging(config.log_level)

    # Load user preferences and let them override config defaults
    preferences_manager = PreferencesManager()
    prefs = preferences_manager.preferences
    if prefs.default_adapter != config.default_adapter:
        config.default_adapter = prefs.default_adapter

    # Wire routing backends
    backend_registry = BackendRegistry()

    # Try to create embedded router (may fail if AuraRouter not installed)
    embedded_backend = None
    try:
        from auracode.routing.embedded import EmbeddedRouterBackend

        embedded_backend = EmbeddedRouterBackend(config.router_config_path)
    except ImportError:
        log.debug("aurarouter_not_available")

    # If grid configured, try failover setup
    default_backend: Any = None
    if config.grid_endpoint:
        try:
            from auracode.grid.client import GridDelegateBackend
            from auracode.grid.failover import FailoverBackend

            grid_backend = GridDelegateBackend(config.grid_endpoint)
            if embedded_backend:
                default_backend = FailoverBackend(
                    grid_backend, embedded_backend, config.local_context_limit
                )
            else:
                default_backend = grid_backend
        except ImportError:
            log.debug("grid_deps_not_available")
            default_backend = embedded_backend
    else:
        default_backend = embedded_backend

    if default_backend:
        backend_registry.register("default", default_backend)

    # Apply user's analyzer preference (non-critical — never blocks startup)
    if prefs.active_analyzer and default_backend:
        try:
            import asyncio as _aio

            try:
                loop = _aio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Already inside an event loop — schedule as a task.
                # The preference will be applied once the loop processes it.
                loop.create_task(default_backend.set_active_analyzer(prefs.active_analyzer))
            else:
                _aio.run(default_backend.set_active_analyzer(prefs.active_analyzer))
        except Exception:
            pass  # Non-critical — analyzer preference is best-effort

    # Wire adapters
    adapter_registry = AdapterRegistry()
    discover_adapters(adapter_registry)

    # Create engine (needs a backend — use a stub if none available)
    router = backend_registry.get_default() if default_backend else _create_stub_backend()
    engine = AuraCodeEngine(config, router)

    return engine, adapter_registry, backend_registry, preferences_manager


def _create_stub_backend():
    """Create a stub backend that returns helpful error messages."""
    from auracode.models.context import SessionContext
    from auracode.models.request import RequestIntent
    from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult

    class StubBackend(BaseRouterBackend):
        """Placeholder backend when no real router is configured."""

        async def route(
            self,
            prompt: str,
            intent: RequestIntent,
            context: SessionContext | None = None,
            options: dict[str, Any] | None = None,
        ) -> RouteResult:
            return RouteResult(
                content=(
                    "No routing backend configured. "
                    "Install AuraRouter or configure a grid endpoint."
                ),
                model_used="none",
            )

        async def list_models(self) -> list[ModelInfo]:
            return []

        async def health_check(self) -> bool:
            return False

    return StubBackend()
