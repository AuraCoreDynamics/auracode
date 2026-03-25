"""Tests for the Codestral adapter, CLI, and formatter."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from auracode.adapters.codestral.adapter import CodestralAdapter
from auracode.adapters.codestral.cli import codestral
from auracode.adapters.codestral.formatter import format_response
from auracode.adapters.loader import discover_adapters
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    RequestIntent,
    TokenUsage,
)


@pytest.fixture()
def adapter() -> CodestralAdapter:
    return CodestralAdapter()


@pytest.fixture()
def sample_response() -> EngineResponse:
    return EngineResponse(
        request_id="cds-001",
        content="return sorted(items, key=lambda x: x.name)",
        model_used="codestral-latest",
        usage=TokenUsage(prompt_tokens=15, completion_tokens=25),
    )


@pytest.fixture()
def sample_response_with_artifacts() -> EngineResponse:
    return EngineResponse(
        request_id="cds-002",
        content="Completed the function.",
        model_used="codestral-latest",
        artifacts=[
            FileArtifact(
                path="utils.py",
                content="def sort_items(items):\n    return sorted(items)\n",
                action="create",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------


class TestCodestralAdapter:
    def test_name(self, adapter: CodestralAdapter) -> None:
        assert adapter.name == "codestral"

    @pytest.mark.asyncio
    async def test_translate_request_complete(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "def sort(", "intent": "complete"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.COMPLETE_CODE
        assert req.prompt == "def sort("
        assert req.adapter_name == "codestral"
        assert req.request_id

    @pytest.mark.asyncio
    async def test_translate_request_fill(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "fill in the middle", "intent": "fill"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE

    @pytest.mark.asyncio
    async def test_translate_request_chat(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "What is a closure?", "intent": "chat"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.CHAT

    @pytest.mark.asyncio
    async def test_translate_request_default_intent(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "def foo("}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.COMPLETE_CODE  # default is complete

    @pytest.mark.asyncio
    async def test_translate_request_unknown_intent(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "Something", "intent": "unknown_thing"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.COMPLETE_CODE  # falls back to complete

    @pytest.mark.asyncio
    async def test_translate_request_with_options(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "Hello", "options": {"model": "codestral-latest"}}
        req = await adapter.translate_request(raw)
        assert req.options["model"] == "codestral-latest"

    @pytest.mark.asyncio
    async def test_translate_request_fim_options(self, adapter: CodestralAdapter) -> None:
        raw = {
            "prompt": "middle part",
            "intent": "complete",
            "options": {"prefix": "def foo():\n    ", "suffix": "\n    return result"},
        }
        req = await adapter.translate_request(raw)
        assert req.options["prefix"] == "def foo():\n    "
        assert req.options["suffix"] == "\n    return result"

    @pytest.mark.asyncio
    async def test_translate_request_with_context_files(
        self, adapter: CodestralAdapter, tmp_path
    ) -> None:
        test_file = tmp_path / "module.py"
        test_file.write_text("import os", encoding="utf-8")
        raw = {"prompt": "complete", "context_files": [str(test_file)]}
        req = await adapter.translate_request(raw)
        assert req.context is not None
        assert len(req.context.files) == 1
        assert req.context.files[0].content == "import os"
        assert req.context.files[0].language == "py"

    @pytest.mark.asyncio
    async def test_translate_request_no_context(self, adapter: CodestralAdapter) -> None:
        raw = {"prompt": "Hello"}
        req = await adapter.translate_request(raw)
        assert req.context is None

    @pytest.mark.asyncio
    async def test_translate_request_type_error(self, adapter: CodestralAdapter) -> None:
        with pytest.raises(TypeError):
            await adapter.translate_request([1, 2, 3])

    @pytest.mark.asyncio
    async def test_translate_response_raw_code(
        self, adapter: CodestralAdapter, sample_response: EngineResponse
    ) -> None:
        result = await adapter.translate_response(sample_response)
        assert isinstance(result, str)
        assert "sorted(items" in result
        # Raw output — no markdown fencing.
        assert "```" not in result

    @pytest.mark.asyncio
    async def test_translate_response_with_artifacts(
        self, adapter: CodestralAdapter, sample_response_with_artifacts: EngineResponse
    ) -> None:
        result = await adapter.translate_response(sample_response_with_artifacts)
        assert "def sort_items" in result
        assert "Completed the function." in result

    def test_get_cli_group(self, adapter: CodestralAdapter) -> None:
        group = adapter.get_cli_group()
        assert group is not None
        assert group.name == "codestral"

    def test_cli_group_has_subcommands(self, adapter: CodestralAdapter) -> None:
        group = adapter.get_cli_group()
        assert "complete" in group.commands
        assert "fill" in group.commands
        assert "chat" in group.commands


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestCodestralFormatter:
    def test_format_raw_content(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response)
        assert "sorted(items" in output
        assert "```" not in output

    def test_format_artifact_content(self, sample_response_with_artifacts: EngineResponse) -> None:
        output = format_response(sample_response_with_artifacts)
        assert "def sort_items" in output

    def test_format_delete_artifact(self) -> None:
        resp = EngineResponse(
            request_id="x",
            content="",
            artifacts=[FileArtifact(path="old.py", content="", action="delete")],
        )
        output = format_response(resp)
        assert "deleted" in output
        assert "old.py" in output

    def test_format_error(self) -> None:
        resp = EngineResponse(request_id="x", content="", error="rate limited")
        output = format_response(resp)
        assert "Error" in output
        assert "rate limited" in output

    def test_format_content_only(self) -> None:
        resp = EngineResponse(request_id="x", content="Just chatting")
        output = format_response(resp)
        assert "Just chatting" in output


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCodestralCLI:
    def _make_mock_app(self, content="codestral mock response"):
        from unittest.mock import AsyncMock, MagicMock

        resp = EngineResponse(request_id="cds-mock", content=content, model_used="mock")
        engine = MagicMock()
        engine.execute = AsyncMock(return_value=resp)
        adapter_reg = AdapterRegistry()
        from auracode.adapters.codestral.adapter import CodestralAdapter

        adapter_reg.register(CodestralAdapter())
        return (engine, adapter_reg, MagicMock(), MagicMock())

    def test_complete_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("completion result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(codestral, ["complete", "def sort("])
        assert result.exit_code == 0
        assert "completion result" in result.output

    def test_fill_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("fill result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(codestral, ["fill", "fill middle"])
        assert result.exit_code == 0
        assert "fill result" in result.output

    def test_chat_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("chat result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(codestral, ["chat", "what is FIM"])
        assert result.exit_code == 0
        assert "chat result" in result.output


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


class TestCodestralDiscovery:
    def test_register_adds_to_registry(self) -> None:
        from auracode.adapters.codestral import register

        registry = AdapterRegistry()
        register(registry)
        assert "codestral" in registry.list_adapters()

    def test_discover_finds_codestral(self) -> None:
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
        assert "codestral" in registry.list_adapters()
