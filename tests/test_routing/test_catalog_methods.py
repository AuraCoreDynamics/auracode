"""Tests for catalog methods on EmbeddedRouterBackend."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock

import pytest

from auracode.routing.base import AnalyzerInfo, ServiceInfo

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_backend():
    """(Re-)import EmbeddedRouterBackend so it picks up mocked modules."""
    import auracode.routing.embedded as mod

    importlib.reload(mod)
    return mod.EmbeddedRouterBackend


def _make_config_with_catalog(
    *,
    catalog: dict | None = None,
    active_analyzer: str | None = None,
) -> MagicMock:
    """Build a mock ConfigLoader that supports catalog methods."""
    from tests.test_routing.conftest import _build_mock_config_loader

    cfg = {
        "models": {
            "local-coder": {"provider": "ollama", "tags": ["local"]},
        },
        "roles": {
            "coder": ["local-coder"],
        },
    }
    if catalog:
        cfg["catalog"] = catalog
    if active_analyzer:
        cfg["system"] = {"active_analyzer": active_analyzer}
    return _build_mock_config_loader(cfg)


# ---------------------------------------------------------------------------
# EmbeddedRouterBackend.list_services
# ---------------------------------------------------------------------------


class TestListServices:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_returns_services_from_catalog(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        catalog = {
            "svc-1": {
                "kind": "service",
                "display_name": "Service One",
                "description": "Test service",
                "provider": "acme",
                "endpoint": "http://svc1:8080",
                "tools": ["tool_a"],
                "status": "active",
            },
        }
        mocks["config_loader"] = _make_config_with_catalog(catalog=catalog)
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        services = await backend.list_services()
        assert len(services) == 1
        assert isinstance(services[0], ServiceInfo)
        assert services[0].service_id == "svc-1"
        assert services[0].display_name == "Service One"
        assert services[0].endpoint == "http://svc1:8080"
        assert services[0].tools == ["tool_a"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_empty_catalog_returns_empty(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"] = _make_config_with_catalog()
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        services = await backend.list_services()
        assert services == []

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_exception_returns_empty(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"].catalog_list = MagicMock(side_effect=RuntimeError("boom"))
        cls = _import_backend()
        backend = cls()

        services = await backend.list_services()
        assert services == []


# ---------------------------------------------------------------------------
# EmbeddedRouterBackend.list_analyzers
# ---------------------------------------------------------------------------


class TestListAnalyzers:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_returns_analyzers_with_active_marker(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        catalog = {
            "a1": {
                "kind": "analyzer",
                "display_name": "Analyzer One",
                "description": "First",
                "analyzer_kind": "intent_triage",
                "provider": "aurarouter",
                "capabilities": ["code"],
            },
            "a2": {
                "kind": "analyzer",
                "display_name": "Analyzer Two",
                "description": "Second",
                "analyzer_kind": "ml",
                "provider": "remote",
                "capabilities": ["reasoning"],
            },
        }
        mocks["config_loader"] = _make_config_with_catalog(catalog=catalog, active_analyzer="a1")
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        analyzers = await backend.list_analyzers()
        assert len(analyzers) == 2
        by_id = {a.analyzer_id: a for a in analyzers}
        assert by_id["a1"].is_active is True
        assert by_id["a2"].is_active is False
        assert by_id["a1"].kind == "intent_triage"
        assert by_id["a2"].capabilities == ["reasoning"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_exception_returns_empty(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"].catalog_list = MagicMock(side_effect=RuntimeError("fail"))
        cls = _import_backend()
        backend = cls()

        analyzers = await backend.list_analyzers()
        assert analyzers == []


# ---------------------------------------------------------------------------
# EmbeddedRouterBackend.get_active_analyzer
# ---------------------------------------------------------------------------


class TestGetActiveAnalyzer:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_returns_active_analyzer(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        catalog = {
            "a1": {
                "kind": "analyzer",
                "display_name": "Active Analyzer",
                "description": "Desc",
                "analyzer_kind": "intent_triage",
                "provider": "aurarouter",
                "capabilities": ["code", "reasoning"],
            },
        }
        mocks["config_loader"] = _make_config_with_catalog(catalog=catalog, active_analyzer="a1")
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        active = await backend.get_active_analyzer()
        assert active is not None
        assert isinstance(active, AnalyzerInfo)
        assert active.analyzer_id == "a1"
        assert active.is_active is True
        assert active.capabilities == ["code", "reasoning"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_returns_none_when_no_active(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"] = _make_config_with_catalog()
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        active = await backend.get_active_analyzer()
        assert active is None

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_returns_none_when_id_not_in_catalog(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"] = _make_config_with_catalog(active_analyzer="nonexistent")
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        active = await backend.get_active_analyzer()
        assert active is None

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_exception_returns_none(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"].get_active_analyzer = MagicMock(side_effect=RuntimeError("fail"))
        cls = _import_backend()
        backend = cls()

        active = await backend.get_active_analyzer()
        assert active is None


# ---------------------------------------------------------------------------
# EmbeddedRouterBackend.set_active_analyzer
# ---------------------------------------------------------------------------


class TestSetActiveAnalyzer:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_set_calls_config(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"] = _make_config_with_catalog()
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        result = await backend.set_active_analyzer("new-analyzer")
        assert result is True
        mocks["config_loader"].set_active_analyzer.assert_called_once_with("new-analyzer")

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_clear_calls_config_with_none(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"] = _make_config_with_catalog()
        mocks["config_cls"].return_value = mocks["config_loader"]

        cls = _import_backend()
        backend = cls()

        result = await backend.set_active_analyzer(None)
        assert result is True
        mocks["config_loader"].set_active_analyzer.assert_called_once_with(None)

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_exception_returns_false(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"].set_active_analyzer = MagicMock(side_effect=RuntimeError("fail"))
        cls = _import_backend()
        backend = cls()

        result = await backend.set_active_analyzer("x")
        assert result is False


# ---------------------------------------------------------------------------
# StubBackend (base class defaults)
# ---------------------------------------------------------------------------


class TestStubBackendDefaults:
    """The base class defaults return empty/False for all catalog methods."""

    async def test_list_services_empty(self):
        from auracode.app import _create_stub_backend

        stub = _create_stub_backend()

        services = await stub.list_services()
        assert services == []

    async def test_list_analyzers_empty(self):
        from auracode.app import _create_stub_backend

        stub = _create_stub_backend()

        analyzers = await stub.list_analyzers()
        assert analyzers == []

    async def test_get_active_analyzer_none(self):
        from auracode.app import _create_stub_backend

        stub = _create_stub_backend()

        active = await stub.get_active_analyzer()
        assert active is None

    async def test_set_active_analyzer_false(self):
        from auracode.app import _create_stub_backend

        stub = _create_stub_backend()

        result = await stub.set_active_analyzer("x")
        assert result is False
