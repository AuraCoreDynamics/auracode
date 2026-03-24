"""Integration tests for catalog functionality and engine + analyzer interaction."""

from __future__ import annotations

import sys
from typing import Any

import pytest
import structlog

from auracode.engine.core import AuraCodeEngine
from auracode.engine.preferences import PreferencesManager
from auracode.engine.registry import AdapterRegistry, BackendRegistry
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent, TokenUsage
from auracode.routing.base import (
    AnalyzerInfo,
    BaseRouterBackend,
    ModelInfo,
    RouteResult,
    ServiceInfo,
)


# ---------------------------------------------------------------------------
# Mock backend with catalog support
# ---------------------------------------------------------------------------


class CatalogMockBackend(BaseRouterBackend):
    """Backend implementing catalog methods for integration testing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._active_analyzer: str | None = None
        self._services: list[ServiceInfo] = [
            ServiceInfo(
                service_id="svc-001",
                display_name="Code Search",
                description="Semantic code search",
                provider="mock",
                tools=["search_code", "find_symbols"],
                status="registered",
            ),
        ]
        self._analyzers: list[AnalyzerInfo] = [
            AnalyzerInfo(
                analyzer_id="analyze-001",
                display_name="Complexity Analyzer",
                description="Measures cyclomatic complexity",
                kind="static",
                provider="mock",
                capabilities=["complexity", "nesting"],
                is_active=False,
            ),
        ]

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        self.calls.append({"prompt": prompt, "intent": intent})
        return RouteResult(
            content=f"catalog response to: {prompt}",
            model_used="catalog-mock-v1",
            usage=TokenUsage(prompt_tokens=5, completion_tokens=10),
        )

    async def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(model_id="catalog-model", provider="mock")]

    async def health_check(self) -> bool:
        return True

    async def list_services(self) -> list[ServiceInfo]:
        return list(self._services)

    async def list_analyzers(self) -> list[AnalyzerInfo]:
        analyzers = []
        for a in self._analyzers:
            analyzers.append(
                a.model_copy(update={"is_active": a.analyzer_id == self._active_analyzer})
            )
        return analyzers

    async def get_active_analyzer(self) -> AnalyzerInfo | None:
        for a in self._analyzers:
            if a.analyzer_id == self._active_analyzer:
                return a.model_copy(update={"is_active": True})
        return None

    async def set_active_analyzer(self, analyzer_id: str | None) -> bool:
        if analyzer_id is None:
            self._active_analyzer = None
            return True
        for a in self._analyzers:
            if a.analyzer_id == analyzer_id:
                self._active_analyzer = analyzer_id
                return True
        return False

    async def catalog_summary(self) -> dict[str, int]:
        return await super().catalog_summary()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def catalog_backend() -> CatalogMockBackend:
    return CatalogMockBackend()


@pytest.fixture()
def catalog_engine(catalog_backend: CatalogMockBackend) -> AuraCodeEngine:
    config = AuraCodeConfig(log_level="WARNING")
    return AuraCodeEngine(config, catalog_backend)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCatalogSummary:
    async def test_summary_counts(self, catalog_backend: CatalogMockBackend) -> None:
        summary = await catalog_backend.catalog_summary()
        assert summary["models"] == 1
        assert summary["services"] == 1
        assert summary["analyzers"] == 1

    async def test_services_details(self, catalog_backend: CatalogMockBackend) -> None:
        services = await catalog_backend.list_services()
        assert len(services) == 1
        svc = services[0]
        assert svc.service_id == "svc-001"
        assert svc.display_name == "Code Search"
        assert "search_code" in svc.tools
        assert svc.status == "registered"


class TestAnalyzerLifecycle:
    async def test_activate_analyzer(self, catalog_backend: CatalogMockBackend) -> None:
        result = await catalog_backend.set_active_analyzer("analyze-001")
        assert result is True
        active = await catalog_backend.get_active_analyzer()
        assert active is not None
        assert active.analyzer_id == "analyze-001"
        assert active.is_active is True

    async def test_deactivate_analyzer(self, catalog_backend: CatalogMockBackend) -> None:
        await catalog_backend.set_active_analyzer("analyze-001")
        result = await catalog_backend.set_active_analyzer(None)
        assert result is True
        active = await catalog_backend.get_active_analyzer()
        assert active is None

    async def test_set_nonexistent_analyzer_fails(self, catalog_backend: CatalogMockBackend) -> None:
        result = await catalog_backend.set_active_analyzer("does-not-exist")
        assert result is False


class TestEngineWithAnalyzer:
    async def test_execute_works_with_active_analyzer(
        self, catalog_engine: AuraCodeEngine, catalog_backend: CatalogMockBackend
    ) -> None:
        """Engine.execute() works when an analyzer is active on the backend."""
        await catalog_backend.set_active_analyzer("analyze-001")

        req = EngineRequest(
            request_id="cat-001",
            intent=RequestIntent.REVIEW,
            prompt="Check complexity",
            adapter_name="test",
        )
        resp = await catalog_engine.execute(req)
        assert resp.error is None
        assert "catalog response" in resp.content
        assert resp.model_used == "catalog-mock-v1"
        # Verify the call went through
        assert len(catalog_backend.calls) == 1
        assert catalog_backend.calls[0]["intent"] == RequestIntent.REVIEW


class TestPreferencesManagerInBootstrap:
    def test_preferences_manager_is_returned(self, tmp_path) -> None:
        """Verify PreferencesManager can be instantiated with a custom path."""
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        assert mgr.preferences.default_adapter == "opencode"
        assert mgr.preferences.history_limit == 100
        # Set and verify a preference round-trips
        mgr.set("history_limit", 50)
        assert mgr.preferences.history_limit == 50
        # Reload from disk and verify persistence
        mgr2 = PreferencesManager(prefs_path=prefs_file)
        assert mgr2.preferences.history_limit == 50
