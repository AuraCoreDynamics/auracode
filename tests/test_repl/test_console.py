"""Tests for the interactive REPL console."""

from __future__ import annotations

import pytest

from auracode.models.request import RequestIntent
from auracode.repl.console import AuraCodeConsole


class TestConsoleInit:
    """Console initialization."""

    def test_default_adapter_set(self, console: AuraCodeConsole):
        assert console.active_adapter is not None
        assert console.active_adapter.name == "opencode"

    def test_empty_initial_state(self, console: AuraCodeConsole):
        assert console.context_files == []
        assert console.session_history == []
        assert console.running is False

    def test_unknown_default_adapter(self, engine, adapter_registry):
        console = AuraCodeConsole(engine, adapter_registry, default_adapter_name="nonexistent")
        assert console.active_adapter is None


class TestIntentDetection:
    """Intent is detected from the first word of the prompt."""

    @pytest.mark.parametrize("text, expected", [
        ("explain main.py", RequestIntent.EXPLAIN_CODE),
        ("review server.py", RequestIntent.REVIEW),
        ("plan a REST API", RequestIntent.PLAN),
        ("edit the config loader", RequestIntent.EDIT_CODE),
        ("generate a parser", RequestIntent.GENERATE_CODE),
        ("write unit tests", RequestIntent.GENERATE_CODE),
        ("create a new module", RequestIntent.GENERATE_CODE),
        ("implement the handler", RequestIntent.GENERATE_CODE),
        ("complete this function", RequestIntent.COMPLETE_CODE),
        ("how does this work?", RequestIntent.CHAT),
        ("what is dependency injection?", RequestIntent.CHAT),
        ("", RequestIntent.CHAT),
    ])
    def test_intent_from_prefix(self, console: AuraCodeConsole, text, expected):
        assert console._detect_intent(text) == expected


class TestSendPrompt:
    """Sending prompts through the engine."""

    async def test_basic_prompt(self, console: AuraCodeConsole):
        result = await console.send_prompt("hello world")
        assert result is not None
        assert "Echo: hello world" in result

    async def test_prompt_updates_history(self, console: AuraCodeConsole):
        await console.send_prompt("first prompt")
        assert len(console.session_history) == 2  # user + assistant
        assert console.session_history[0]["role"] == "user"
        assert console.session_history[0]["content"] == "first prompt"
        assert console.session_history[1]["role"] == "assistant"

    async def test_multiple_prompts_accumulate_history(self, console: AuraCodeConsole):
        await console.send_prompt("one")
        await console.send_prompt("two")
        assert len(console.session_history) == 4

    async def test_intent_hint_overrides_detection(self, console: AuraCodeConsole, mock_backend):
        await console.send_prompt("hello", intent_hint="review")
        assert mock_backend.last_intent == RequestIntent.REVIEW

    async def test_no_adapter_returns_message(self, console: AuraCodeConsole):
        console.active_adapter = None
        result = await console.send_prompt("test")
        assert "No adapter active" in result

    async def test_detected_intent_reaches_backend(self, console: AuraCodeConsole, mock_backend):
        await console.send_prompt("explain main.py")
        assert mock_backend.last_intent == RequestIntent.EXPLAIN_CODE

    async def test_chat_intent_for_plain_prompt(self, console: AuraCodeConsole, mock_backend):
        await console.send_prompt("what is a monad?")
        assert mock_backend.last_intent == RequestIntent.CHAT


class TestSessionContext:
    """Context building from files and history."""

    def test_no_context_when_empty(self, console: AuraCodeConsole):
        ctx = console._build_session_context()
        assert ctx is None

    async def test_history_included_in_context(self, console: AuraCodeConsole):
        await console.send_prompt("first")
        ctx = console._build_session_context()
        assert ctx is not None
        assert len(ctx.history) == 2

    def test_files_included_in_context(self, console: AuraCodeConsole):
        from auracode.models.context import FileContext
        console.context_files.append(
            FileContext(path="test.py", content="print('hi')", language="py")
        )
        ctx = console._build_session_context()
        assert ctx is not None
        assert len(ctx.files) == 1
        assert ctx.files[0].path == "test.py"
