"""Shared fixtures for REPL tests."""

from __future__ import annotations

from typing import Any

import pytest

from auracode.adapters.base import BaseAdapter
from auracode.engine.core import AuraCodeEngine
from auracode.engine.registry import AdapterRegistry
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent
from auracode.repl.console import AuraCodeConsole
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult

import click


class MockRouterBackend(BaseRouterBackend):
    """Router that echoes the prompt back as the response."""

    def __init__(self) -> None:
        self.last_prompt: str | None = None
        self.last_intent: RequestIntent | None = None

    async def route(
        self, prompt: str, intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        self.last_prompt = prompt
        self.last_intent = intent
        return RouteResult(
            content=f"Echo: {prompt}",
            model_used="mock-model",
        )

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(model_id="mock-local", provider="ollama", tags=["fast"]),
            ModelInfo(model_id="mock-cloud", provider="claude", tags=["reasoning"]),
        ]

    async def health_check(self) -> bool:
        return True


class MockAdapter(BaseAdapter):
    """Simple mock adapter for testing."""

    def __init__(self, name: str = "mock-adapter") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def translate_request(self, raw_input: Any) -> EngineRequest:
        raise NotImplementedError

    async def translate_response(self, response: EngineResponse) -> Any:
        return response.content

    def get_cli_group(self) -> click.Group | None:
        return None


@pytest.fixture()
def mock_backend() -> MockRouterBackend:
    return MockRouterBackend()


@pytest.fixture()
def engine(mock_backend: MockRouterBackend) -> AuraCodeEngine:
    config = AuraCodeConfig()
    return AuraCodeEngine(config, mock_backend)


@pytest.fixture()
def adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    registry.register(MockAdapter("opencode"))
    registry.register(MockAdapter("claude-code"))
    registry.register(MockAdapter("copilot"))
    registry.register(MockAdapter("aider"))
    return registry


@pytest.fixture()
def console(engine: AuraCodeEngine, adapter_registry: AdapterRegistry) -> AuraCodeConsole:
    return AuraCodeConsole(engine, adapter_registry, default_adapter_name="opencode")
