"""Tests for FailoverBackend catalog methods."""

from __future__ import annotations

from typing import Any

import pytest

from auracode.grid.failover import FailoverBackend
from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent, TokenUsage
from auracode.routing.base import (
    AnalyzerInfo,
    BaseRouterBackend,
    ModelInfo,
    RouteResult,
    ServiceInfo,
)


# ---------------------------------------------------------------------------
# Helper backend with catalog support
# ---------------------------------------------------------------------------


class CatalogMockBackend(BaseRouterBackend):
    """Backend with configurable catalog results."""

    def __init__(
        self,
        *,
        healthy: bool = True,
        services: list[ServiceInfo] | None = None,
        analyzers: list[AnalyzerInfo] | None = None,
        active_analyzer: AnalyzerInfo | None = None,
        set_analyzer_result: bool = True,
        catalog_error: Exception | None = None,
    ) -> None:
        self.healthy = healthy
        self._services = services or []
        self._analyzers = analyzers or []
        self._active_analyzer = active_analyzer
        self._set_analyzer_result = set_analyzer_result
        self._catalog_error = catalog_error
        self.set_analyzer_calls: list[str | None] = []

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        return RouteResult(content="mock", model_used="mock", usage=None)

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def health_check(self) -> bool:
        return self.healthy

    async def list_services(self) -> list[ServiceInfo]:
        if self._catalog_error:
            raise self._catalog_error
        return list(self._services)

    async def list_analyzers(self) -> list[AnalyzerInfo]:
        if self._catalog_error:
            raise self._catalog_error
        return list(self._analyzers)

    async def get_active_analyzer(self) -> AnalyzerInfo | None:
        if self._catalog_error:
            raise self._catalog_error
        return self._active_analyzer

    async def set_active_analyzer(self, analyzer_id: str | None) -> bool:
        self.set_analyzer_calls.append(analyzer_id)
        if self._catalog_error:
            raise self._catalog_error
        return self._set_analyzer_result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFailoverListServices:
    async def test_merges_and_deduplicates(self):
        shared = ServiceInfo(service_id="svc-shared", display_name="Shared")
        primary = CatalogMockBackend(services=[
            ServiceInfo(service_id="svc-p", display_name="Primary"),
            shared,
        ])
        fallback = CatalogMockBackend(services=[
            ServiceInfo(service_id="svc-f", display_name="Fallback"),
            shared,
        ])

        fo = FailoverBackend(primary, fallback)
        services = await fo.list_services()

        ids = [s.service_id for s in services]
        assert ids.count("svc-shared") == 1
        assert "svc-p" in ids
        assert "svc-f" in ids

    async def test_primary_failure_returns_fallback(self):
        primary = CatalogMockBackend(catalog_error=RuntimeError("boom"))
        fallback = CatalogMockBackend(services=[
            ServiceInfo(service_id="svc-f", display_name="Fallback"),
        ])

        fo = FailoverBackend(primary, fallback)
        services = await fo.list_services()
        assert len(services) == 1
        assert services[0].service_id == "svc-f"


class TestFailoverListAnalyzers:
    async def test_merges_and_deduplicates(self):
        shared = AnalyzerInfo(analyzer_id="a-shared", display_name="Shared")
        primary = CatalogMockBackend(analyzers=[
            AnalyzerInfo(analyzer_id="a-p", display_name="Primary"),
            shared,
        ])
        fallback = CatalogMockBackend(analyzers=[
            AnalyzerInfo(analyzer_id="a-f", display_name="Fallback"),
            shared,
        ])

        fo = FailoverBackend(primary, fallback)
        analyzers = await fo.list_analyzers()

        ids = [a.analyzer_id for a in analyzers]
        assert ids.count("a-shared") == 1
        assert "a-p" in ids
        assert "a-f" in ids


class TestFailoverGetActiveAnalyzer:
    async def test_delegates_to_primary(self):
        active = AnalyzerInfo(analyzer_id="a1", display_name="Active", is_active=True)
        primary = CatalogMockBackend(active_analyzer=active)
        fallback = CatalogMockBackend(active_analyzer=None)

        fo = FailoverBackend(primary, fallback)
        result = await fo.get_active_analyzer()
        assert result is not None
        assert result.analyzer_id == "a1"

    async def test_falls_back_when_primary_returns_none(self):
        active = AnalyzerInfo(analyzer_id="a2", display_name="Fallback Active", is_active=True)
        primary = CatalogMockBackend(active_analyzer=None)
        fallback = CatalogMockBackend(active_analyzer=active)

        fo = FailoverBackend(primary, fallback)
        result = await fo.get_active_analyzer()
        assert result is not None
        assert result.analyzer_id == "a2"

    async def test_falls_back_when_primary_errors(self):
        active = AnalyzerInfo(analyzer_id="a2", display_name="Fallback Active", is_active=True)
        primary = CatalogMockBackend(catalog_error=RuntimeError("boom"))
        fallback = CatalogMockBackend(active_analyzer=active)

        fo = FailoverBackend(primary, fallback)
        result = await fo.get_active_analyzer()
        assert result is not None
        assert result.analyzer_id == "a2"

    async def test_returns_none_when_both_none(self):
        primary = CatalogMockBackend(active_analyzer=None)
        fallback = CatalogMockBackend(active_analyzer=None)

        fo = FailoverBackend(primary, fallback)
        result = await fo.get_active_analyzer()
        assert result is None


class TestFailoverSetActiveAnalyzer:
    async def test_delegates_to_primary(self):
        primary = CatalogMockBackend(set_analyzer_result=True)
        fallback = CatalogMockBackend(set_analyzer_result=True)

        fo = FailoverBackend(primary, fallback)
        result = await fo.set_active_analyzer("a1")
        assert result is True
        assert primary.set_analyzer_calls == ["a1"]
        assert fallback.set_analyzer_calls == []

    async def test_falls_back_when_primary_returns_false(self):
        primary = CatalogMockBackend(set_analyzer_result=False)
        fallback = CatalogMockBackend(set_analyzer_result=True)

        fo = FailoverBackend(primary, fallback)
        result = await fo.set_active_analyzer("a1")
        assert result is True
        assert primary.set_analyzer_calls == ["a1"]
        assert fallback.set_analyzer_calls == ["a1"]

    async def test_falls_back_when_primary_errors(self):
        primary = CatalogMockBackend(catalog_error=RuntimeError("boom"))
        fallback = CatalogMockBackend(set_analyzer_result=True)

        fo = FailoverBackend(primary, fallback)
        result = await fo.set_active_analyzer("a1")
        assert result is True

    async def test_returns_false_when_both_fail(self):
        primary = CatalogMockBackend(set_analyzer_result=False)
        fallback = CatalogMockBackend(set_analyzer_result=False)

        fo = FailoverBackend(primary, fallback)
        result = await fo.set_active_analyzer("a1")
        assert result is False
