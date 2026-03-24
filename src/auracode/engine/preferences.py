"""Preferences manager — load/save user preferences to YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from auracode.models.preferences import _PREFS_FILE, UserPreferences


class PreferencesManager:
    """Manages persistent user preferences stored as YAML."""

    def __init__(self, prefs_path: Path | None = None) -> None:
        self._path = prefs_path or _PREFS_FILE
        self._preferences: UserPreferences = self._load_from_disk()

    def _load_from_disk(self) -> UserPreferences:
        """Load preferences from YAML file, returning defaults on any error."""
        if not self._path.exists():
            return UserPreferences()
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = yaml.safe_load(raw)
            if not isinstance(data, dict):
                return UserPreferences()
            return UserPreferences(**data)
        except Exception:
            return UserPreferences()

    def load(self) -> UserPreferences:
        """Reload preferences from disk. Returns defaults if no file exists."""
        self._preferences = self._load_from_disk()
        return self._preferences

    def save(self) -> None:
        """Persist current preferences to YAML, creating directories as needed."""
        prefs_dir = self._path.parent
        prefs_dir.mkdir(parents=True, exist_ok=True)
        data = self._preferences.model_dump()
        self._path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

    def get(self, key: str) -> Any:
        """Get a preference value by key. Raises AttributeError for unknown keys."""
        if not hasattr(self._preferences, key):
            raise AttributeError(f"Unknown preference: {key}")
        return getattr(self._preferences, key)

    def set(self, key: str, value: Any) -> None:
        """Set a preference value by key and persist to disk."""
        if not hasattr(self._preferences, key):
            raise AttributeError(f"Unknown preference: {key}")
        # Coerce types based on the field annotation
        field_info = UserPreferences.model_fields[key]
        current = getattr(self._preferences, key)
        if isinstance(current, bool) or (field_info.annotation is bool):
            if isinstance(value, str):
                value = value.lower() in ("true", "1", "yes", "on")
        elif isinstance(current, int):
            if isinstance(value, str):
                value = int(value)
        data = self._preferences.model_dump()
        data[key] = value
        self._preferences = UserPreferences(**data)
        self.save()

    @property
    def preferences(self) -> UserPreferences:
        """Return the current preferences object."""
        return self._preferences
