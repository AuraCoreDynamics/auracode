"""Session and file context models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FileContext(BaseModel):
    """Represents a single file in the user's working context."""

    model_config = ConfigDict(frozen=True)

    path: str
    content: str | None = None
    language: str | None = None
    selection: tuple[int, int] | None = None


class SessionContext(BaseModel):
    """Snapshot of an active coding session."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    working_directory: str
    files: list[FileContext] = []
    history: list[dict[str, str]] = []
    metadata: dict[str, Any] = {}
    journal: list[dict[str, Any]] = []
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Context semantics for sovereignty/retrieval-aware routing (TG2/TG7).
    project_id: str | None = None
    sensitivity_label: str | None = None
    changed_files: list[str] = []
    diff_summary: str | None = None
    retrieval_hints: list[str] = []
