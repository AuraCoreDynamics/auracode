"""Abstract base class for router backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict

from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent, TokenUsage


class ModelInfo(BaseModel):
    """Descriptor for a model available through a router backend."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    provider: str
    tags: list[str] = []


class RouteResult(BaseModel):
    """The outcome of a single routing + inference call."""

    model_config = ConfigDict(frozen=True)

    content: str
    model_used: str
    usage: TokenUsage | None = None
    metadata: dict[str, Any] = {}


class BaseRouterBackend(ABC):
    """ABC for backends that select a model and execute inference."""

    @abstractmethod
    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        """Route a prompt to an appropriate model and return the result."""
        ...

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """Return all models currently available through this backend."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the backend is reachable and operational."""
        ...
