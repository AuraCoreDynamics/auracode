"""Shared fixtures for grid tests."""

from __future__ import annotations

from typing import Any

import pytest

from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent, TokenUsage
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult

# ---------------------------------------------------------------------------
# Mock backends for failover testing
# ---------------------------------------------------------------------------


class MockBackend(BaseRouterBackend):
    """Fully controllable mock backend."""

    def __init__(
        self,
        *,
        healthy: bool = True,
        route_result: RouteResult | None = None,
        models: list[ModelInfo] | None = None,
        route_error: Exception | None = None,
        health_error: Exception | None = None,
    ) -> None:
        self.healthy = healthy
        self.route_result = route_result or RouteResult(
            content="mock response",
            model_used="mock-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
        )
        self.models = models or []
        self.route_error = route_error
        self.health_error = health_error
        self.route_calls: list[dict[str, Any]] = []
        self.health_calls: int = 0
        self.list_models_calls: int = 0

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        self.route_calls.append(
            {"prompt": prompt, "intent": intent, "context": context, "options": options}
        )
        if self.route_error:
            raise self.route_error
        return self.route_result

    async def list_models(self) -> list[ModelInfo]:
        self.list_models_calls += 1
        return list(self.models)

    async def health_check(self) -> bool:
        self.health_calls += 1
        if self.health_error:
            raise self.health_error
        return self.healthy


@pytest.fixture()
def healthy_primary() -> MockBackend:
    return MockBackend(
        healthy=True,
        route_result=RouteResult(
            content="primary answer",
            model_used="grid-model",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=15),
        ),
        models=[ModelInfo(model_id="grid-model", provider="auragrid", tags=["fast"])],
    )


@pytest.fixture()
def healthy_fallback() -> MockBackend:
    return MockBackend(
        healthy=True,
        route_result=RouteResult(
            content="fallback answer",
            model_used="local-model",
            usage=TokenUsage(prompt_tokens=8, completion_tokens=12),
        ),
        models=[ModelInfo(model_id="local-model", provider="local", tags=["cheap"])],
    )


@pytest.fixture()
def unhealthy_primary() -> MockBackend:
    return MockBackend(healthy=False)


@pytest.fixture()
def failing_primary() -> MockBackend:
    return MockBackend(
        healthy=True,
        route_error=RuntimeError("primary exploded"),
    )
