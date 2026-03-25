"""Tests for Claude Code CLI wiring to the AuraCode engine."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter
from auracode.adapters.claude_code.cli import claude
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import EngineResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_app(response_content: str = "engine says hello"):
    """Build mock (engine, adapter_registry, backend_registry, prefs) tuple."""
    mock_response = EngineResponse(
        request_id="test-001",
        content=response_content,
        model_used="test-model",
    )
    mock_engine = MagicMock()
    mock_engine.execute = AsyncMock(return_value=mock_response)

    adapter_reg = AdapterRegistry()
    adapter_reg.register(ClaudeCodeAdapter())

    return (mock_engine, adapter_reg, MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# T6.2: do command wiring
# ---------------------------------------------------------------------------


class TestDoWiring:
    def test_do_invokes_engine(self):
        """The 'do' command should call engine.execute() and display the result."""
        app_tuple = _make_mock_app("generated code here")
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["do", "Write a hello world"])

        assert result.exit_code == 0
        assert "generated code here" in result.output
        engine.execute.assert_called_once()

    def test_do_passes_prompt_through_adapter(self):
        """Verify the prompt reaches the engine request."""
        app_tuple = _make_mock_app()
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            runner.invoke(claude, ["do", "Build a REST API"])

        # The engine was called; check the request prompt
        call_args = engine.execute.call_args
        request = call_args[0][0]
        assert request.prompt == "Build a REST API"

    def test_do_with_model_option(self):
        """The --model flag should be passed through as an option."""
        app_tuple = _make_mock_app()
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            runner.invoke(claude, ["do", "-m", "opus", "hello"])

        request = engine.execute.call_args[0][0]
        assert request.options.get("model") == "opus"

    def test_do_json_output(self):
        """The --json flag should produce valid JSON output."""
        app_tuple = _make_mock_app("json test")

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["do", "--json", "hello"])

        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data["content"] == "json test"
        assert "request_id" in data


# ---------------------------------------------------------------------------
# T6.3: explain and review command wiring
# ---------------------------------------------------------------------------


class TestExplainWiring:
    def test_explain_reads_file_content(self, tmp_path):
        """explain should read file content and include it in the prompt."""
        test_file = tmp_path / "sample.py"
        test_file.write_text("def foo():\n    return 42\n", encoding="utf-8")

        app_tuple = _make_mock_app("explanation here")
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["explain", str(test_file)])

        assert result.exit_code == 0
        assert "explanation here" in result.output
        engine.execute.assert_called_once()

        # The prompt should contain the file content
        request = engine.execute.call_args[0][0]
        assert "def foo():" in request.prompt
        assert "return 42" in request.prompt

    def test_explain_missing_file_still_works(self):
        """explain on a missing file should still invoke engine with a fallback prompt."""
        app_tuple = _make_mock_app("fallback explanation")
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["explain", "nonexistent.py"])

        assert result.exit_code == 0
        assert "fallback explanation" in result.output
        engine.execute.assert_called_once()

    def test_explain_includes_file_in_context(self, tmp_path):
        """explain should pass the file path as context."""
        test_file = tmp_path / "ctx.py"
        test_file.write_text("x = 1", encoding="utf-8")

        app_tuple = _make_mock_app()
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            runner.invoke(claude, ["explain", str(test_file)])

        request = engine.execute.call_args[0][0]
        # The file should be in context
        assert request.context is not None
        paths = [f.path for f in request.context.files]
        assert str(test_file) in paths


class TestReviewWiring:
    def test_review_reads_file_content(self, tmp_path):
        """review should read file content and include it in the prompt."""
        test_file = tmp_path / "review_me.py"
        test_file.write_text("class Bad:\n    pass\n", encoding="utf-8")

        app_tuple = _make_mock_app("review feedback")
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["review", str(test_file)])

        assert result.exit_code == 0
        assert "review feedback" in result.output
        engine.execute.assert_called_once()

        request = engine.execute.call_args[0][0]
        assert "class Bad:" in request.prompt

    def test_review_missing_file_still_works(self):
        """review on a missing file should still invoke engine."""
        app_tuple = _make_mock_app("fallback review")
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["review", "gone.py"])

        assert result.exit_code == 0
        assert "fallback review" in result.output
        engine.execute.assert_called_once()


# ---------------------------------------------------------------------------
# T6.4: chat command wiring
# ---------------------------------------------------------------------------


class TestChatWiring:
    def test_chat_handles_ctrl_c(self):
        """chat should exit gracefully on KeyboardInterrupt."""
        app_tuple = _make_mock_app()

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            # Simulate immediate EOF (no input) which triggers click.Abort
            result = runner.invoke(claude, ["chat"], input="")

        # Should exit cleanly (not crash)
        assert result.exit_code == 0

    def test_chat_processes_input(self):
        """chat should send user input to the engine and display response."""
        app_tuple = _make_mock_app("chat reply")
        engine = app_tuple[0]

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            # Provide one line of input, then EOF
            result = runner.invoke(claude, ["chat"], input="hello there\n")

        assert "chat reply" in result.output
        engine.execute.assert_called_once()


# ---------------------------------------------------------------------------
# T6.5: Engine unavailability
# ---------------------------------------------------------------------------


class TestEngineUnavailable:
    def test_graceful_error_on_bootstrap_failure(self):
        """When create_application raises, the CLI should show a helpful error."""
        with patch(
            "auracode.app.create_application",
            side_effect=RuntimeError("AuraRouter not installed"),
        ):
            runner = CliRunner()
            result = runner.invoke(claude, ["do", "hello"])

        assert result.exit_code != 0
        assert "Error" in result.output or "Error" in (result.output + str(result.exception or ""))

    def test_stub_backend_returns_helpful_message(self):
        """When using stub backend, engine returns a helpful message (not a crash)."""
        # Use a real stub response that mimics what StubBackend would produce
        stub_response = EngineResponse(
            request_id="stub-001",
            content="No routing backend configured. Install \
                AuraRouter or configure a grid endpoint.",
        )
        mock_engine = MagicMock()
        mock_engine.execute = AsyncMock(return_value=stub_response)

        adapter_reg = AdapterRegistry()
        adapter_reg.register(ClaudeCodeAdapter())
        app_tuple = (mock_engine, adapter_reg, MagicMock(), MagicMock())

        with patch("auracode.app.create_application", return_value=app_tuple):
            runner = CliRunner()
            result = runner.invoke(claude, ["do", "hello"])

        assert result.exit_code == 0
        assert "No routing backend configured" in result.output


# ---------------------------------------------------------------------------
# No placeholder calls remain
# ---------------------------------------------------------------------------


class TestNoPlaceholders:
    def test_no_placeholder_response_function(self):
        """Verify _placeholder_response has been removed from the cli module."""
        from auracode.adapters.claude_code import cli as cli_module

        assert not hasattr(cli_module, "_placeholder_response")
