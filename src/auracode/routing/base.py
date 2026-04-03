"""Abstract base class for router backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
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


class ServiceInfo(BaseModel):
    """Descriptor for an MCP service in the catalog."""

    model_config = ConfigDict(frozen=True)

    service_id: str
    display_name: str
    description: str = ""
    provider: str = ""
    endpoint: str = ""
    tools: list[str] = []
    status: str = "registered"


class AnalyzerInfo(BaseModel):
    """Descriptor for a route analyzer in the catalog."""

    model_config = ConfigDict(frozen=True)

    analyzer_id: str
    display_name: str
    description: str = ""
    kind: str = ""
    provider: str = ""
    capabilities: list[str] = []
    is_active: bool = False


class BackendCapability(BaseModel):
    """Describes a single capability a backend supports."""

    model_config = ConfigDict(frozen=True)

    capability_id: str
    supported: bool = True
    description: str = ""


class RouteResult(BaseModel):
    """The outcome of a single routing + inference call."""

    model_config = ConfigDict(frozen=True)

    content: str
    model_used: str
    usage: TokenUsage | None = None
    metadata: dict[str, Any] = {}
    degradations: list[Any] = []


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

    # ── Streaming (default falls back to non-streaming) ────────────

    async def route_stream(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Yield response tokens incrementally.

        The default implementation calls :meth:`route` and yields the
        complete response as a single chunk.  Backends that support true
        streaming should override this method.
        """
        result = await self.route(prompt, intent, context, options)
        # Stash metadata for retrieval after streaming completes.
        self._last_stream_result = result
        yield result.content

    def get_last_stream_result(self) -> RouteResult | None:
        """Return the RouteResult from the most recent stream, if available."""
        return getattr(self, "_last_stream_result", None)

    # ── Optional catalog methods (default implementations) ────────────

    async def list_services(self) -> list[ServiceInfo]:
        """Return all services currently available through this backend."""
        return []

    async def list_analyzers(self) -> list[AnalyzerInfo]:
        """Return all route analyzers currently available through this backend."""
        return []

    async def get_active_analyzer(self) -> AnalyzerInfo | None:
        """Return the currently active route analyzer, or None."""
        return None

    async def set_active_analyzer(self, analyzer_id: str | None) -> bool:
        """Set the active route analyzer. Returns True on success."""
        return False

    async def get_capabilities(self) -> list[BackendCapability]:
        """Return capabilities supported by this backend."""
        return []

    async def catalog_summary(self) -> dict[str, int]:
        """Return a summary of catalog counts."""
        models = await self.list_models()
        services = await self.list_services()
        analyzers = await self.list_analyzers()
        return {"models": len(models), "services": len(services), "analyzers": len(analyzers)}
