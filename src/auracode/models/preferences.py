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
    # FMoE preference fields (TG8)
    default_execution_mode: str = "standard"
    default_sovereignty_enforcement: str = "none"
    default_sensitivity_label: str | None = None
    default_retrieval_mode: str = "disabled"
    default_routing_preference: str = "auto"
