"""Tests for the EmbeddedRouterBackend (fully mocked AuraRouter)."""

from __future__ import annotations

import importlib

import pytest

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import ModelInfo, RouteResult

# ---------------------------------------------------------------------------
# Helpers — import the backend *after* the patch fixture activates.
# ---------------------------------------------------------------------------


def _import_backend():
    """(Re-)import EmbeddedRouterBackend so it picks up mocked modules."""
    import auracode.routing.embedded as mod

    importlib.reload(mod)
    return mod.EmbeddedRouterBackend


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEmbeddedInit:
    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_init_creates_config_and_fabric(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        cls = _import_backend()
        cls(config_path="/fake/path.yaml")

        mocks["config_cls"].assert_called_once_with(config_path="/fake/path.yaml")
        mocks["fabric_cls"].assert_called_once_with(config=mocks["config_loader"])

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_init_no_config_path(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        cls = _import_backend()
        cls()  # no config_path
        mocks["config_cls"].assert_called_once_with(config_path=None)


class TestEmbeddedRoute:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_generate_code(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        cls = _import_backend()
        backend = cls()

        result = await backend.route(
            prompt="Write a function",
            intent=RequestIntent.GENERATE_CODE,
        )

        assert isinstance(result, RouteResult)
        assert result.content == "generated code"
        assert result.model_used == "local-coder"
        mocks["fabric"].execute.assert_called_once()
        call_args = mocks["fabric"].execute.call_args
        assert call_args[0][0] == "coder"  # role
        assert "Write a function" in call_args[0][1]  # prompt

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_explain_code_uses_reasoning(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        cls = _import_backend()
        backend = cls()

        result = await backend.route(
            prompt="Explain this code",
            intent=RequestIntent.EXPLAIN_CODE,
        )

        assert result.model_used == "cloud-reasoning"
        call_args = mocks["fabric"].execute.call_args
        assert call_args[0][0] == "reasoning"

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_includes_context(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        cls = _import_backend()
        backend = cls()

        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[FileContext(path="app.py", content="import os")],
        )

        await backend.route(
            prompt="Add logging",
            intent=RequestIntent.EDIT_CODE,
            context=ctx,
        )

        full_prompt = mocks["fabric"].execute.call_args[0][1]
        assert "app.py" in full_prompt
        assert "import os" in full_prompt
        assert "Add logging" in full_prompt

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_fabric_returns_none_raises(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["fabric"].execute.return_value = None
        cls = _import_backend()
        backend = cls()

        with pytest.raises(RuntimeError, match="All models failed"):
            await backend.route(
                prompt="fail",
                intent=RequestIntent.GENERATE_CODE,
            )


class TestEmbeddedListModels:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_list_models_returns_all(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()

        models = await backend.list_models()
        assert len(models) == 2
        ids = {m.model_id for m in models}
        assert ids == {"local-coder", "cloud-reasoning"}
        for m in models:
            assert isinstance(m, ModelInfo)


class TestEmbeddedHealthCheck:
    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_health_check_ok(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        assert await backend.health_check() is True

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_health_check_empty_config(self, _patch_aurarouter):
        mocks = _patch_aurarouter
        mocks["config_loader"].config = {}
        cls = _import_backend()
        backend = cls()
        assert await backend.health_check() is False
