"""Fixtures for integration tests."""

from __future__ import annotations

import sys
from typing import Any

import pytest
import structlog

from auracode.engine.core import AuraCodeEngine
from auracode.engine.registry import AdapterRegistry, BackendRegistry
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, RequestIntent, TokenUsage
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult


class IntegrationMockBackend(BaseRouterBackend):
    """Deterministic backend that records calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        self.calls.append(
            {
                "prompt": prompt,
                "intent": intent,
                "context": context,
                "options": options,
            }
        )
        return RouteResult(
            content=f"integration mock response to: {prompt}",
            model_used="integration-mock-v1",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=15),
        )

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(model_id="integration-mock-v1", provider="mock", tags=["integration"]),
            ModelInfo(model_id="integration-mock-v2", provider="mock", tags=["integration", "large"]),
        ]

    async def health_check(self) -> bool:
        return True


@pytest.fixture()
def mock_backend() -> IntegrationMockBackend:
    """A mock backend that records calls."""
    return IntegrationMockBackend()


@pytest.fixture()
def integration_config() -> AuraCodeConfig:
    """Config with no grid endpoint (pure local mode)."""
    return AuraCodeConfig(log_level="WARNING")


@pytest.fixture()
def app_components(
    mock_backend: IntegrationMockBackend,
    integration_config: AuraCodeConfig,
) -> tuple[AuraCodeEngine, AdapterRegistry, BackendRegistry]:
    """Bootstrap application with mocked backend."""
    # Reset structlog to avoid stale stderr references from earlier tests
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )

    backend_registry = BackendRegistry()
    backend_registry.register("default", mock_backend)

    adapter_registry = AdapterRegistry()
    # Register adapters directly to avoid structlog/stderr issues in tests
    from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter
    from auracode.adapters.openai_shim.adapter import OpenAIShimAdapter
    from auracode.adapters.opencode.adapter import OpenCodeAdapter

    adapter_registry.register(ClaudeCodeAdapter())
    adapter_registry.register(OpenAIShimAdapter())
    adapter_registry.register(OpenCodeAdapter())

    engine = AuraCodeEngine(integration_config, mock_backend)
    return engine, adapter_registry, backend_registry
