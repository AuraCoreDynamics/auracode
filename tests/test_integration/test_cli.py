"""Tests for the unified CLI."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from auracode.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


class TestCLIHelp:
    """Basic CLI structure tests."""

    def test_help_shows_all_commands(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "models" in result.output
        assert "serve" in result.output
        assert "repl" in result.output

    def test_version_flag(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestStatusCommand:
    """Tests for 'auracode status'."""

    def test_status_runs(self, runner):
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "AuraCode Status" in result.output
        assert "Adapters:" in result.output
        assert "Router:" in result.output
        assert "Models:" in result.output

    def test_status_shows_adapters(self, runner):
        result = runner.invoke(main, ["status"])
        assert result.exit_code == 0
        assert "opencode" in result.output


class TestModelsCommand:
    """Tests for 'auracode models'."""

    def test_models_runs(self, runner):
        """Run 'auracode models' — expect either 'No models available' or model names."""
        result = runner.invoke(main, ["models"])
        assert result.exit_code == 0
        # With a real backend models are listed; with stub, "No models available."
        has_models = "(" in result.output  # model lines look like "  name (provider)"
        has_no_models = "No models available" in result.output
        assert has_models or has_no_models, f"Unexpected output: {result.output!r}"


class TestServeCommand:
    """Tests for 'auracode serve'."""

    def test_serve_help(self, runner):
        result = runner.invoke(main, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--host" in result.output

    def test_serve_import_error_message(self, runner):
        """Verify that missing aiohttp produces an error message containing 'aiohttp'."""
        import sys

        # Temporarily hide aiohttp to trigger the ImportError path
        saved = sys.modules.get("aiohttp")
        saved_web = sys.modules.get("aiohttp.web")
        sys.modules["aiohttp"] = None  # type: ignore[assignment]
        sys.modules["aiohttp.web"] = None  # type: ignore[assignment]
        try:
            result = runner.invoke(main, ["serve"])
        finally:
            if saved is not None:
                sys.modules["aiohttp"] = saved
            else:
                sys.modules.pop("aiohttp", None)
            if saved_web is not None:
                sys.modules["aiohttp.web"] = saved_web
            else:
                sys.modules.pop("aiohttp.web", None)
        assert result.exit_code != 0
        assert "aiohttp" in result.output
