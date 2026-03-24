"""Tests for the engine, session manager, and registries."""

from __future__ import annotations

from typing import Any

import click
import pytest

from auracode.adapters.base import BaseAdapter
from auracode.engine.core import AuraCodeEngine
from auracode.engine.registry import AdapterRegistry, BackendRegistry
from auracode.engine.session import SessionManager
from auracode.models.config import AuraCodeConfig
from auracode.models.request import (
    EngineRequest,
    EngineResponse,
    RequestIntent,
)
from auracode.routing.base import BaseRouterBackend

# We reuse the fixtures from conftest (mock_backend, failing_backend, etc.)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------

class TestSessionManager:
    def test_create(self) -> None:
        sm = SessionManager()
        ctx = sm.create("/workspace")
        assert ctx.working_directory == "/workspace"
        assert len(ctx.session_id) > 0

    def test_get(self) -> None:
        sm = SessionManager()
        ctx = sm.create("/ws")
        found = sm.get(ctx.session_id)
        assert found is not None
        assert found.session_id == ctx.session_id

    def test_get_missing(self) -> None:
        sm = SessionManager()
        assert sm.get("nonexistent") is None

    def test_update(self, sample_request: EngineRequest, sample_response: EngineResponse) -> None:
        sm = SessionManager()
        ctx = sm.create("/ws")
        updated = sm.update(ctx.session_id, sample_request, sample_response)
        assert len(updated.history) == 2
        assert updated.history[0]["role"] == "user"
        assert updated.history[1]["role"] == "assistant"

    def test_update_missing_raises(self, sample_request: EngineRequest, sample_response: EngineResponse) -> None:
        sm = SessionManager()
        with pytest.raises(KeyError):
            sm.update("missing", sample_request, sample_response)

    def test_close(self) -> None:
        sm = SessionManager()
        ctx = sm.create("/ws")
        sm.close(ctx.session_id)
        assert sm.get(ctx.session_id) is None

    def test_close_missing_noop(self) -> None:
        sm = SessionManager()
        sm.close("does-not-exist")  # should not raise


# ---------------------------------------------------------------------------
# AuraCodeEngine
# ---------------------------------------------------------------------------

class TestAuraCodeEngine:
    @pytest.fixture()
    def engine(self, default_config: AuraCodeConfig, mock_backend: BaseRouterBackend) -> AuraCodeEngine:
        return AuraCodeEngine(config=default_config, router=mock_backend)

    @pytest.mark.asyncio
    async def test_execute_success(self, engine: AuraCodeEngine, sample_request: EngineRequest) -> None:
        resp = await engine.execute(sample_request)
        assert resp.request_id == sample_request.request_id
        assert "mock response" in resp.content
        assert resp.model_used == "mock-model-v1"
        assert resp.error is None

    @pytest.mark.asyncio
    async def test_execute_error_path(
        self,
        default_config: AuraCodeConfig,
        failing_backend: BaseRouterBackend,
        sample_request: EngineRequest,
    ) -> None:
        engine = AuraCodeEngine(config=default_config, router=failing_backend)
        resp = await engine.execute(sample_request)
        assert resp.error is not None
        assert "backend unavailable" in resp.error

    def test_session_lifecycle(self, engine: AuraCodeEngine) -> None:
        ctx = engine.session_manager.create("/project")
        sid = ctx.session_id
        assert engine.get_session(sid) is not None
        engine.close_session(sid)
        assert engine.get_session(sid) is None

    @pytest.mark.asyncio
    async def test_execute_creates_session(self, engine: AuraCodeEngine) -> None:
        """Verify execute() creates a session visible in session_manager."""
        # Session manager should be empty before execute
        assert len(engine.session_manager._sessions) == 0

        req = EngineRequest(
            request_id="sess-test-001",
            intent=RequestIntent.CHAT,
            prompt="Hello engine",
            adapter_name="test",
        )
        resp = await engine.execute(req)
        assert resp.error is None

        # After execute, session_manager must contain exactly one session
        assert len(engine.session_manager._sessions) == 1
        session_id = list(engine.session_manager._sessions.keys())[0]
        session = engine.session_manager.get(session_id)
        assert session is not None
        assert session.working_directory == "."
        # Session history should have 2 entries: user prompt + assistant response
        assert len(session.history) == 2
        assert session.history[0]["content"] == "Hello engine"
        assert session.history[1]["role"] == "assistant"


# ---------------------------------------------------------------------------
# AdapterRegistry
# ---------------------------------------------------------------------------

class _StubAdapter(BaseAdapter):
    """Minimal concrete adapter for registry testing."""

    def __init__(self, adapter_name: str) -> None:
        self._name = adapter_name

    @property
    def name(self) -> str:
        return self._name

    async def translate_request(self, raw_input: Any) -> EngineRequest:
        raise NotImplementedError

    async def translate_response(self, response: EngineResponse) -> Any:
        raise NotImplementedError

    def get_cli_group(self) -> click.Group | None:
        return None


class TestAdapterRegistry:
    def test_register_and_get(self) -> None:
        reg = AdapterRegistry()
        adapter = _StubAdapter("alpha")
        reg.register(adapter)
        assert reg.get("alpha") is adapter

    def test_get_missing(self) -> None:
        reg = AdapterRegistry()
        assert reg.get("nope") is None

    def test_list_adapters(self) -> None:
        reg = AdapterRegistry()
        reg.register(_StubAdapter("a"))
        reg.register(_StubAdapter("b"))
        names = reg.list_adapters()
        assert set(names) == {"a", "b"}

    def test_overwrite(self) -> None:
        reg = AdapterRegistry()
        reg.register(_StubAdapter("x"))
        replacement = _StubAdapter("x")
        reg.register(replacement)
        assert reg.get("x") is replacement


# ---------------------------------------------------------------------------
# BackendRegistry
# ---------------------------------------------------------------------------

class TestBackendRegistry:
    def test_register_and_get(self, mock_backend: BaseRouterBackend) -> None:
        reg = BackendRegistry()
        reg.register("mock", mock_backend)
        assert reg.get("mock") is mock_backend

    def test_default_is_first_registered(self, mock_backend: BaseRouterBackend) -> None:
        reg = BackendRegistry()
        reg.register("first", mock_backend)
        assert reg.get_default() is mock_backend

    def test_explicit_default(
        self,
        mock_backend: BaseRouterBackend,
        failing_backend: BaseRouterBackend,
    ) -> None:
        reg = BackendRegistry()
        reg.register("a", mock_backend)
        reg.register("b", failing_backend, default=True)
        assert reg.get_default() is failing_backend

    def test_list_backends(self, mock_backend: BaseRouterBackend) -> None:
        reg = BackendRegistry()
        reg.register("x", mock_backend)
        reg.register("y", mock_backend)
        assert set(reg.list_backends()) == {"x", "y"}

    def test_get_default_empty(self) -> None:
        reg = BackendRegistry()
        assert reg.get_default() is None
