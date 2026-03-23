"""Fixtures for shim server tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from auracode.models.request import EngineResponse, TokenUsage
from auracode.routing.base import ModelInfo
from auracode.shim.server import create_app


class _MockRouter:
    """Minimal mock router for model listing."""

    async def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo(model_id="mock-model-v1", provider="mock", tags=["test"]),
            ModelInfo(model_id="mock-model-v2", provider="mock", tags=["fast"]),
        ]


class _MockEngine:
    """Mock engine that returns deterministic responses."""

    def __init__(self) -> None:
        self.router = _MockRouter()
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, request: Any) -> EngineResponse:
        return EngineResponse(
            request_id=request.request_id,
            content=f"mock response to: {request.prompt}",
            model_used="mock-model-v1",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
        )


@pytest.fixture()
def mock_engine() -> _MockEngine:
    return _MockEngine()


@pytest.fixture()
def app(mock_engine: _MockEngine):
    return create_app(mock_engine)


@pytest.fixture()
async def client(aiohttp_client, app):
    return await aiohttp_client(app)
