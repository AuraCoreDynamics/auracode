"""Tests for UserPreferences model and PreferencesManager."""

from __future__ import annotations

import pytest

from auracode.models.preferences import UserPreferences
from auracode.engine.preferences import PreferencesManager


class TestUserPreferences:
    """UserPreferences model defaults."""

    def test_default_adapter_is_opencode(self):
        prefs = UserPreferences()
        assert prefs.default_adapter == "opencode"

    def test_show_model_in_response_default(self):
        prefs = UserPreferences()
        assert prefs.show_model_in_response is True

    def test_show_token_usage_default(self):
        prefs = UserPreferences()
        assert prefs.show_token_usage is False

    def test_history_limit_default(self):
        prefs = UserPreferences()
        assert prefs.history_limit == 100

    def test_markdown_rendering_default(self):
        prefs = UserPreferences()
        assert prefs.markdown_rendering is True

    def test_prefer_local_default(self):
        prefs = UserPreferences()
        assert prefs.prefer_local is False

    def test_active_analyzer_default(self):
        prefs = UserPreferences()
        assert prefs.active_analyzer is None


class TestPreferencesManager:
    """PreferencesManager load/save/get/set."""

    def test_returns_defaults_when_no_file(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        assert mgr.preferences.default_adapter == "opencode"
        assert mgr.preferences.history_limit == 100

    def test_save_creates_file(self, tmp_path):
        prefs_file = tmp_path / "subdir" / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.save()
        assert prefs_file.exists()

    def test_directory_creation_on_save(self, tmp_path):
        prefs_file = tmp_path / "deep" / "nested" / "dir" / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.save()
        assert prefs_file.parent.is_dir()
        assert prefs_file.exists()

    def test_load_save_roundtrip(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.set("default_adapter", "claude-code")
        mgr.set("history_limit", "50")

        # Load fresh from disk
        mgr2 = PreferencesManager(prefs_path=prefs_file)
        assert mgr2.preferences.default_adapter == "claude-code"
        assert mgr2.preferences.history_limit == 50

    def test_get_returns_value(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        assert mgr.get("default_adapter") == "opencode"
        assert mgr.get("history_limit") == 100

    def test_get_unknown_key_raises(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        with pytest.raises(AttributeError, match="Unknown preference"):
            mgr.get("nonexistent_key")

    def test_set_string_value(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.set("default_adapter", "aider")
        assert mgr.get("default_adapter") == "aider"

    def test_set_int_value_from_string(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.set("history_limit", "200")
        assert mgr.get("history_limit") == 200

    def test_set_bool_value_from_string(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.set("show_token_usage", "true")
        assert mgr.get("show_token_usage") is True
        mgr.set("show_token_usage", "false")
        assert mgr.get("show_token_usage") is False

    def test_set_unknown_key_raises(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        with pytest.raises(AttributeError, match="Unknown preference"):
            mgr.set("nonexistent_key", "value")

    def test_load_reloads_from_disk(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        mgr = PreferencesManager(prefs_path=prefs_file)
        mgr.set("default_adapter", "aider")

        # Externally modify the file
        prefs_file.write_text("default_adapter: copilot\n", encoding="utf-8")
        result = mgr.load()
        assert result.default_adapter == "copilot"
        assert mgr.preferences.default_adapter == "copilot"

    def test_handles_invalid_yaml_gracefully(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        prefs_file.write_text(":::invalid yaml{{{", encoding="utf-8")
        mgr = PreferencesManager(prefs_path=prefs_file)
        # Should return defaults, not crash
        assert mgr.preferences.default_adapter == "opencode"

    def test_handles_non_dict_yaml(self, tmp_path):
        prefs_file = tmp_path / "prefs.yaml"
        prefs_file.write_text("just a string\n", encoding="utf-8")
        mgr = PreferencesManager(prefs_path=prefs_file)
        assert mgr.preferences.default_adapter == "opencode"

