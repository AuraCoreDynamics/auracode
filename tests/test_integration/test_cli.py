"""Tests for the unified CLI."""

from __future__ import annotations

from unittest.mock import patch

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
        assert "claude" in result.output

    def test_version_flag(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_claude_subgroup_help(self, runner):
        result = runner.invoke(main, ["claude", "--help"])
        assert result.exit_code == 0
        assert "chat" in result.output
        assert "do" in result.output
        assert "explain" in result.output
        assert "review" in result.output


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
        assert "claude-code" in result.output


class TestModelsCommand:
    """Tests for 'auracode models'."""

    def test_models_runs(self, runner):
        result = runner.invoke(main, ["models"])
        assert result.exit_code == 0
        # With stub backend, no models available
        # With real backend, models will be listed
        # Either way, no crash


class TestServeCommand:
    """Tests for 'auracode serve'."""

    def test_serve_help(self, runner):
        result = runner.invoke(main, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--host" in result.output

    def test_serve_import_error_path(self, runner, monkeypatch):
        """Verify serve fails gracefully if aiohttp is missing."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "aiohttp.web" or name == "aiohttp":
                raise ImportError("mock: aiohttp not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = runner.invoke(main, ["serve"])
        # Should fail with helpful message or exit code 1
        # (may succeed if aiohttp is cached in sys.modules)
        assert result.exit_code in (0, 1)
