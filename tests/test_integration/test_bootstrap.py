"""Tests for application bootstrap (create_application)."""

from __future__ import annotations

import os

import pytest

from auracode.app import create_application, load_config
from auracode.engine.core import AuraCodeEngine
from auracode.engine.preferences import PreferencesManager
from auracode.engine.registry import AdapterRegistry, BackendRegistry
from auracode.models.config import AuraCodeConfig


class TestLoadConfig:
    """Tests for config loading."""

    def test_load_defaults_when_no_file(self, tmp_path, monkeypatch):
        """Returns default AuraCodeConfig when no config file exists."""
        monkeypatch.chdir(tmp_path)
        config = load_config(None)
        assert isinstance(config, AuraCodeConfig)
        assert config.grid_endpoint is None
        assert config.log_level == "INFO"

    def test_load_from_explicit_path(self, tmp_path):
        """Loads config from an explicit yaml file."""
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text("log_level: DEBUG\ngrid_endpoint: localhost:9090\n")
        config = load_config(str(cfg_file))
        assert config.log_level == "DEBUG"
        assert config.grid_endpoint == "localhost:9090"

    def test_load_from_default_location(self, tmp_path, monkeypatch):
        """Picks up auracode.yaml from cwd."""
        monkeypatch.chdir(tmp_path)
        cfg_file = tmp_path / "auracode.yaml"
        cfg_file.write_text("default_adapter: openai-shim\n")
        config = load_config(None)
        assert config.default_adapter == "openai-shim"

    def test_load_ignores_nonexistent_explicit_path(self):
        """Falls through to defaults when explicit path doesn't exist."""
        config = load_config("/nonexistent/auracode.yaml")
        assert isinstance(config, AuraCodeConfig)


class TestCreateApplication:
    """Tests for full application bootstrap."""

    def test_bootstrap_with_defaults(self):
        """create_application() succeeds with no config file."""
        engine, adapters, backends, prefs = create_application()
        assert isinstance(engine, AuraCodeEngine)
        assert isinstance(adapters, AdapterRegistry)
        assert isinstance(backends, BackendRegistry)
        assert isinstance(prefs, PreferencesManager)

    def test_engine_has_working_backend(self):
        """Engine has a router backend (stub at minimum)."""
        engine, _, _, _ = create_application()
        assert engine.router is not None

    def test_adapter_registry_contains_claude_code(self):
        """Adapter registry discovers the claude-code adapter."""
        _, adapters, _, _ = create_application()
        names = adapters.list_adapters()
        assert "claude-code" in names

    def test_adapter_registry_contains_openai_shim(self):
        """Adapter registry discovers the openai-shim adapter."""
        _, adapters, _, _ = create_application()
        names = adapters.list_adapters()
        assert "openai-shim" in names

    def test_grid_backend_not_created_when_no_endpoint(self):
        """BackendRegistry does not have grid when grid_endpoint is None."""
        _, _, backends, _ = create_application()
        # With no AuraRouter installed, default will be stub (not in registry)
        # With AuraRouter installed, default will be embedded
        # Either way, there should be no "grid" backend
        assert backends.get("grid") is None

    def test_engine_router_is_set(self):
        """Engine always has a router backend assigned."""
        engine, _, _, _ = create_application()
        assert engine.router is not None
        # The router should implement the BaseRouterBackend interface
        from auracode.routing.base import BaseRouterBackend
        assert isinstance(engine.router, BaseRouterBackend)
