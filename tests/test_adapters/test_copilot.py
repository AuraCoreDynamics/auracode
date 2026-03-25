"""Tests for the Copilot adapter, CLI, and formatter."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from auracode.adapters.copilot.adapter import CopilotAdapter
from auracode.adapters.copilot.cli import copilot
from auracode.adapters.copilot.formatter import format_response
from auracode.adapters.loader import discover_adapters
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    RequestIntent,
    TokenUsage,
)


@pytest.fixture()
def adapter() -> CopilotAdapter:
    return CopilotAdapter()


@pytest.fixture()
def sample_response() -> EngineResponse:
    return EngineResponse(
        request_id="cop-001",
        content="This function greets the user.",
        model_used="copilot-model",
        usage=TokenUsage(prompt_tokens=20, completion_tokens=40),
        artifacts=[
            FileArtifact(
                path="src/greet.py",
                content="def greet(name):\n    return f'Hello, {name}!'\n",
                action="create",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------


class TestCopilotAdapter:
    def test_name(self, adapter: CopilotAdapter) -> None:
        assert adapter.name == "copilot"

    @pytest.mark.asyncio
    async def test_translate_request_suggest(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Write a sort function", "intent": "suggest"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE
        assert req.prompt == "Write a sort function"
        assert req.adapter_name == "copilot"
        assert req.request_id  # non-empty UUID string

    @pytest.mark.asyncio
    async def test_translate_request_explain(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Explain this code", "intent": "explain"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.EXPLAIN_CODE

    @pytest.mark.asyncio
    async def test_translate_request_commit(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Write commit message", "intent": "commit"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE
        assert req.options.get("commit") is True

    @pytest.mark.asyncio
    async def test_translate_request_default_intent(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Something"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE  # default is suggest

    @pytest.mark.asyncio
    async def test_translate_request_unknown_intent(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Something", "intent": "unknown_thing"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE  # falls back to generate

    @pytest.mark.asyncio
    async def test_translate_request_with_options(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Hello", "options": {"model": "gpt-4"}}
        req = await adapter.translate_request(raw)
        assert req.options["model"] == "gpt-4"

    @pytest.mark.asyncio
    async def test_translate_request_workspace_root(self, adapter: CopilotAdapter) -> None:
        raw = {
            "prompt": "Hello",
            "context_files": ["fake.py"],
            "options": {"workspace_root": "/my/project"},
        }
        req = await adapter.translate_request(raw)
        assert req.context is not None
        assert req.context.working_directory == "/my/project"

    @pytest.mark.asyncio
    async def test_translate_request_with_context_files(
        self, adapter: CopilotAdapter, tmp_path
    ) -> None:
        test_file = tmp_path / "example.js"
        test_file.write_text("console.log('hi')", encoding="utf-8")
        raw = {"prompt": "Explain", "context_files": [str(test_file)]}
        req = await adapter.translate_request(raw)
        assert req.context is not None
        assert len(req.context.files) == 1
        assert req.context.files[0].content == "console.log('hi')"
        assert req.context.files[0].language == "js"

    @pytest.mark.asyncio
    async def test_translate_request_no_context(self, adapter: CopilotAdapter) -> None:
        raw = {"prompt": "Hello"}
        req = await adapter.translate_request(raw)
        assert req.context is None

    @pytest.mark.asyncio
    async def test_translate_request_type_error(self, adapter: CopilotAdapter) -> None:
        with pytest.raises(TypeError):
            await adapter.translate_request("not a dict")

    @pytest.mark.asyncio
    async def test_translate_response(
        self, adapter: CopilotAdapter, sample_response: EngineResponse
    ) -> None:
        result = await adapter.translate_response(sample_response)
        assert isinstance(result, str)
        assert "## Suggestion" in result
        assert "greet.py" in result

    @pytest.mark.asyncio
    async def test_translate_response_with_explanation(
        self, adapter: CopilotAdapter, sample_response: EngineResponse
    ) -> None:
        result = await adapter.translate_response(sample_response)
        assert "## Explanation" in result
        assert "This function greets the user." in result

    def test_get_cli_group(self, adapter: CopilotAdapter) -> None:
        group = adapter.get_cli_group()
        assert group is not None
        assert group.name == "copilot"

    def test_cli_group_has_subcommands(self, adapter: CopilotAdapter) -> None:
        group = adapter.get_cli_group()
        assert "suggest" in group.commands
        assert "explain" in group.commands
        assert "commit" in group.commands


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestCopilotFormatter:
    def test_format_with_artifacts(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response)
        assert "## Suggestion" in output
        assert "```py" in output
        assert "def greet" in output

    def test_format_explanation_section(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response)
        assert "## Explanation" in output
        assert "This function greets the user." in output

    def test_format_content_only(self) -> None:
        resp = EngineResponse(request_id="x", content="Just an explanation")
        output = format_response(resp)
        assert "Just an explanation" in output
        assert "## Suggestion" not in output

    def test_format_error(self) -> None:
        resp = EngineResponse(request_id="x", content="", error="timeout")
        output = format_response(resp)
        assert "Error" in output
        assert "timeout" in output

    def test_format_delete_artifact(self) -> None:
        resp = EngineResponse(
            request_id="x",
            content="Removed",
            artifacts=[FileArtifact(path="old.py", content="", action="delete")],
        )
        output = format_response(resp)
        assert "deleted" in output


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCopilotCLI:
    def _make_mock_app(self, content="copilot mock response"):
        from unittest.mock import AsyncMock, MagicMock

        resp = EngineResponse(request_id="cop-mock", content=content, model_used="mock")
        engine = MagicMock()
        engine.execute = AsyncMock(return_value=resp)
        adapter_reg = AdapterRegistry()
        from auracode.adapters.copilot.adapter import CopilotAdapter

        adapter_reg.register(CopilotAdapter())
        return (engine, adapter_reg, MagicMock(), MagicMock())

    def test_suggest_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("suggestion result")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(copilot, ["suggest", "write hello world"])
        assert result.exit_code == 0
        assert "suggestion result" in result.output

    def test_explain_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("explained")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(copilot, ["explain", "this function"])
        assert result.exit_code == 0
        assert "explained" in result.output

    def test_commit_command(self) -> None:
        from unittest.mock import patch

        app_tuple = self._make_mock_app("commit msg")
        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(copilot, ["commit", "summarize changes"])
        assert result.exit_code == 0
        assert "commit msg" in result.output


# ---------------------------------------------------------------------------
# Discovery tests
# ---------------------------------------------------------------------------


class TestCopilotDiscovery:
    def test_register_adds_to_registry(self) -> None:
        from auracode.adapters.copilot import register

        registry = AdapterRegistry()
        register(registry)
        assert "copilot" in registry.list_adapters()

    def test_discover_finds_copilot(self) -> None:
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
        assert "copilot" in registry.list_adapters()
