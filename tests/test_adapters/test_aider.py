"""Tests for the Aider adapter, CLI, and formatter."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from auracode.adapters.aider.adapter import AiderAdapter
from auracode.adapters.aider.cli import aider
from auracode.adapters.aider.formatter import format_response
from auracode.adapters.loader import discover_adapters
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    RequestIntent,
    TokenUsage,
)


@pytest.fixture()
def adapter() -> AiderAdapter:
    return AiderAdapter()


@pytest.fixture()
def sample_response() -> EngineResponse:
    return EngineResponse(
        request_id="aid-001",
        content="Applied changes to parser.",
        model_used="deepseek-coder",
        usage=TokenUsage(prompt_tokens=40, completion_tokens=90),
        artifacts=[
            FileArtifact(
                path="src/parser.py",
                content="def parse(text):\n    return text.split()\n",
                action="modify",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------


class TestAiderAdapter:
    def test_name(self, adapter: AiderAdapter) -> None:
        assert adapter.name == "aider"

    @pytest.mark.asyncio
    async def test_translate_request_code(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "Fix the bug", "intent": "code"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.EDIT_CODE
        assert req.prompt == "Fix the bug"
        assert req.adapter_name == "aider"
        assert req.request_id

    @pytest.mark.asyncio
    async def test_translate_request_ask(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "What does this do?", "intent": "ask"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.CHAT

    @pytest.mark.asyncio
    async def test_translate_request_architect(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "Design a caching layer", "intent": "architect"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.PLAN

    @pytest.mark.asyncio
    async def test_translate_request_default_intent(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "Something"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.EDIT_CODE  # default is code

    @pytest.mark.asyncio
    async def test_translate_request_unknown_intent(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "Something", "intent": "unknown_thing"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.EDIT_CODE  # falls back to edit

    @pytest.mark.asyncio
    async def test_translate_request_with_options(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "Hello", "options": {"model": "opus"}}
        req = await adapter.translate_request(raw)
        assert req.options["model"] == "opus"

    @pytest.mark.asyncio
    async def test_translate_request_readonly_files(self, adapter: AiderAdapter, tmp_path) -> None:
        ro_file = tmp_path / "config.yaml"
        ro_file.write_text("key: value", encoding="utf-8")
        raw = {
            "prompt": "Update config",
            "context_files": [],
            "options": {"readonly_files": [str(ro_file)]},
        }
        req = await adapter.translate_request(raw)
        assert req.context is not None
        assert len(req.context.files) == 1
        assert req.context.files[0].content == "key: value"

    @pytest.mark.asyncio
    async def test_translate_request_with_context_files(
        self, adapter: AiderAdapter, tmp_path
    ) -> None:
        test_file = tmp_path / "example.py"
        test_file.write_text("x = 1", encoding="utf-8")
        raw = {"prompt": "Edit", "context_files": [str(test_file)]}
        req = await adapter.translate_request(raw)
        assert req.context is not None
        assert len(req.context.files) == 1
        assert req.context.files[0].content == "x = 1"
        assert req.context.files[0].language == "py"

    @pytest.mark.asyncio
    async def test_translate_request_no_context(self, adapter: AiderAdapter) -> None:
        raw = {"prompt": "Hello"}
        req = await adapter.translate_request(raw)
        assert req.context is None

    @pytest.mark.asyncio
    async def test_translate_request_type_error(self, adapter: AiderAdapter) -> None:
        with pytest.raises(TypeError):
            await adapter.translate_request(42)

    @pytest.mark.asyncio
    async def test_translate_response(
        self, adapter: AiderAdapter, sample_response: EngineResponse
    ) -> None:
        result = await adapter.translate_response(sample_response)
        assert isinstance(result, str)
        assert "parser.py" in result

    @pytest.mark.asyncio
    async def test_translate_response_diff_format(
        self, adapter: AiderAdapter, sample_response: EngineResponse
    ) -> None:
        result = await adapter.translate_response(sample_response)
        assert "---" in result
        assert "+++" in result

    def test_get_cli_group(self, adapter: AiderAdapter) -> None:
        group = adapter.get_cli_group()
        assert group is not None
        assert group.name == "aider"

    def test_cli_group_has_subcommands(self, adapter: AiderAdapter) -> None:
        group = adapter.get_cli_group()
        assert "code" in group.commands
        assert "ask" in group.commands
        assert "architect" in group.commands


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestAiderFormatter:
    def test_format_modify_artifact(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response)
        assert "--- src/parser.py" in output
        assert "+++ src/parser.py" in output
        assert "+def parse" in output

    def test_format_create_artifact(self) -> None:
        resp = EngineResponse(
            request_id="x",
            content="Created new file",
            artifacts=[FileArtifact(path="new.py", content="print('new')\n", action="create")],
        )
        output = format_response(resp)
        assert "--- /dev/null" in output
        assert "+++ new.py" in output

    def test_format_delete_artifact(self) -> None:
        resp = EngineResponse(
            request_id="x",
            content="Removed file",
            artifacts=[FileArtifact(path="old.py", content="", action="delete")],
        )
        output = format_response(resp)
        assert "--- old.py" in output
        assert "+++ /dev/null" in output

    def test_format_content_only(self) -> None:
        resp = EngineResponse(request_id="x", content="Just a chat message")
        output = format_response(resp)
        assert "Just a chat message" in output
        assert "---" not in output

    def test_format_error(self) -> None:
        resp = EngineResponse(request_id="x", content="", error="model unavailable")
        output = format_response(resp)
        assert "Error" in output
        assert "model unavailable" in output


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestAiderCLI:
    def _make_mock_app(self, content="aider mock response"):
        from unittest.mock import AsyncMock, MagicMock

        resp = EngineResponse(request_id="aid-mock", content=content, model_used="mock")
        engine = MagicMock()
        engine.execute = AsyncMock(return_value=resp)
        adapter_reg = AdapterRegistry()
        from auracode.adapters.aider.adapter import AiderAdapter

        adapter_reg.register(AiderAdapter())
        return (engine, adapter_reg, MagicMock(), MagicMock())

    def test_code_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("code result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(aider, ["code", "fix the bug"])
        assert result.exit_code == 0
        assert "code result" in result.output

    def test_ask_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("ask result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(aider, ["ask", "what is this"])
        assert result.exit_code == 0
        assert "ask result" in result.output

    def test_architect_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("architect result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(aider, ["architect", "plan caching"])
        assert result.exit_code == 0
        assert "architect result" in result.output


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


class TestAiderDiscovery:
    def test_register_adds_to_registry(self) -> None:
        from auracode.adapters.aider import register

        registry = AdapterRegistry()
        register(registry)
        assert "aider" in registry.list_adapters()

    def test_discover_finds_aider(self) -> None:
        import sys

        import structlog

        structlog.configure(
            processors=[structlog.dev.ConsoleRenderer()],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=False,
        )
        registry = AdapterRegistry()
        discover_adapters(registry)
        assert "aider" in registry.list_adapters()
