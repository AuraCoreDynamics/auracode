"""Tests for routing hints extraction and propagation (TG1)."""

from __future__ import annotations

import importlib
import json

import pytest

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent

# ---------------------------------------------------------------------------
# Helper — import backend after mock patching
# ---------------------------------------------------------------------------


def _import_backend():
    """(Re-)import EmbeddedRouterBackend so it picks up mocked modules."""
    import auracode.routing.embedded as mod

    importlib.reload(mod)
    return mod.EmbeddedRouterBackend


# ---------------------------------------------------------------------------
# _extract_languages tests
# ---------------------------------------------------------------------------


class TestExtractLanguages:
    """T1.1 — _extract_languages() helper."""

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_none_context(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        assert backend._extract_languages(None) == []

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_empty_files(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        ctx = SessionContext(session_id="s1", working_directory="/tmp", files=[])
        assert backend._extract_languages(ctx) == []

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_mixed_languages(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="a.py", language="python"),
                FileContext(path="b.rs", language="rust"),
                FileContext(path="c.ts", language="typescript"),
            ],
        )
        result = backend._extract_languages(ctx)
        assert result == ["python", "rust", "typescript"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_duplicate_languages(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="a.py", language="python"),
                FileContext(path="b.py", language="python"),
                FileContext(path="c.rs", language="rust"),
                FileContext(path="d.rs", language="rust"),
            ],
        )
        result = backend._extract_languages(ctx)
        assert result == ["python", "rust"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_files_with_none_language(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="a.py", language="python"),
                FileContext(path="Makefile", language=None),
                FileContext(path="b.txt"),
                FileContext(path="c.go", language="go"),
            ],
        )
        result = backend._extract_languages(ctx)
        assert result == ["go", "python"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_all_none_languages(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="Makefile"),
                FileContext(path="README"),
            ],
        )
        assert backend._extract_languages(ctx) == []

    @pytest.mark.usefixtures("_patch_aurarouter")
    def test_sorted_output(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="z.ts", language="typescript"),
                FileContext(path="a.go", language="go"),
                FileContext(path="m.py", language="python"),
            ],
        )
        result = backend._extract_languages(ctx)
        assert result == ["go", "python", "typescript"]


# ---------------------------------------------------------------------------
# route() options construction tests
# ---------------------------------------------------------------------------


class TestRouteOptionsConstruction:
    """T1.2 — route() builds correct options dict and propagates hints."""

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_builds_options_no_context(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()

        await backend.route(
            prompt="Hello",
            intent=RequestIntent.CHAT,
        )

        opts = backend._last_route_options
        assert opts["intent"] == "chat"
        assert opts["routing_hints"] == []

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_builds_options_with_context(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()

        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="a.py", language="python"),
                FileContext(path="b.rs", language="rust"),
            ],
        )

        await backend.route(
            prompt="Refactor",
            intent=RequestIntent.EDIT_CODE,
            context=ctx,
        )

        opts = backend._last_route_options
        assert opts["intent"] == "edit_code"
        assert opts["routing_hints"] == ["python", "rust"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_route_options_intent_values(self, _patch_aurarouter):
        """Every intent maps to its correct string value."""
        cls = _import_backend()
        backend = cls()

        for intent in RequestIntent:
            await backend.route(prompt="test", intent=intent)
            assert backend._last_route_options["intent"] == intent.value

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_caller_options_merge(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()

        caller_opts = {"custom_key": "custom_value", "temperature": 0.7}
        await backend.route(
            prompt="Hello",
            intent=RequestIntent.GENERATE_CODE,
            options=caller_opts,
        )

        opts = backend._last_route_options
        assert opts["intent"] == "generate_code"
        assert opts["routing_hints"] == []
        assert opts["custom_key"] == "custom_value"
        assert opts["temperature"] == 0.7

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_caller_options_override_defaults(self, _patch_aurarouter):
        """Caller-provided options win on key collision."""
        cls = _import_backend()
        backend = cls()

        caller_opts = {
            "intent": "overridden_intent",
            "routing_hints": ["forced"],
        }
        await backend.route(
            prompt="Hello",
            intent=RequestIntent.CHAT,
            options=caller_opts,
        )

        opts = backend._last_route_options
        assert opts["intent"] == "overridden_intent"
        assert opts["routing_hints"] == ["forced"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_options_are_json_serializable(self, _patch_aurarouter):
        cls = _import_backend()
        backend = cls()

        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="a.py", language="python"),
            ],
        )

        await backend.route(
            prompt="test",
            intent=RequestIntent.GENERATE_CODE,
            context=ctx,
        )

        # Must not raise
        serialized = json.dumps(backend._last_route_options)
        assert isinstance(serialized, str)
        parsed = json.loads(serialized)
        assert parsed["intent"] == "generate_code"
        assert parsed["routing_hints"] == ["python"]

    @pytest.mark.usefixtures("_patch_aurarouter")
    async def test_routing_hints_prefix_in_prompt(self, _patch_aurarouter):
        """The prompt sent to fabric should contain a ROUTE_OPTIONS block."""
        mocks = _patch_aurarouter
        cls = _import_backend()
        backend = cls()

        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[FileContext(path="a.py", language="python")],
        )

        await backend.route(
            prompt="Write code",
            intent=RequestIntent.GENERATE_CODE,
            context=ctx,
        )

        full_prompt = mocks["fabric"].execute.call_args[0][1]
        assert "[ROUTE_OPTIONS]" in full_prompt
        assert "[/ROUTE_OPTIONS]" in full_prompt
        assert '"intent":"generate_code"' in full_prompt
        assert '"routing_hints":["python"]' in full_prompt
        # The user prompt should still be present after the prefix
        assert "Write code" in full_prompt
