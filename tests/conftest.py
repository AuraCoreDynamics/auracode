"""Shared fixtures for AuraCode tests."""

from __future__ import annotations

from typing import Any

import pytest

from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import (
    EngineRequest,
    EngineResponse,
    RequestIntent,
    TokenUsage,
)
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult


# ---------------------------------------------------------------------------
# Mock router backend
# ---------------------------------------------------------------------------

class MockRouterBackend(BaseRouterBackend):
    """Deterministic backend for testing."""

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        return RouteResult(
            content=f"mock response to: {prompt}",
            model_used="mock-model-v1",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
        )

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(model_id="mock-model-v1", provider="mock", tags=["test"]),
        ]

    async def health_check(self) -> bool:
        return True


class FailingRouterBackend(BaseRouterBackend):
    """Backend that always raises, for error-path testing."""

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        raise RuntimeError("backend unavailable")

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def health_check(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_backend() -> MockRouterBackend:
    return MockRouterBackend()


@pytest.fixture()
def failing_backend() -> FailingRouterBackend:
    return FailingRouterBackend()


@pytest.fixture()
def default_config() -> AuraCodeConfig:
    return AuraCodeConfig()


@pytest.fixture()
def sample_request() -> EngineRequest:
    return EngineRequest(
        request_id="req-001",
        intent=RequestIntent.GENERATE_CODE,
        prompt="Write a hello-world function in Python.",
        adapter_name="test-adapter",
    )


@pytest.fixture()
def sample_response() -> EngineResponse:
    return EngineResponse(
        request_id="req-001",
        content="def hello(): print('Hello, world!')",
        model_used="mock-model-v1",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
    )
