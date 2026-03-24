"""User preferences model."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

_PREFS_DIR = Path.home() / ".auracode"
_PREFS_FILE = _PREFS_DIR / "preferences.yaml"


class UserPreferences(BaseModel):
    """Persistent user preferences for AuraCode."""

    default_adapter: str = "opencode"
    show_model_in_response: bool = True
    show_token_usage: bool = False
    history_limit: int = 100
    markdown_rendering: bool = True
    prefer_local: bool = False
    active_analyzer: str | None = None
