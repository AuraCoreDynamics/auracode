"""Request and response domain models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RequestIntent(StrEnum):
    """Classifies the purpose of an engine request."""

    GENERATE_CODE = "generate_code"
    EXPLAIN_CODE = "explain_code"
    EDIT_CODE = "edit_code"
    COMPLETE_CODE = "complete_code"
    CHAT = "chat"
    PLAN = "plan"
    REVIEW = "review"


class TokenUsage(BaseModel):
    """Token consumption for a single request/response cycle."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0


class FileArtifact(BaseModel):
    """A file produced or modified by the engine."""

    model_config = ConfigDict(frozen=True)

    path: str
    content: str
    action: Literal["create", "modify", "delete"]


class EngineRequest(BaseModel):
    """Immutable request object flowing into the engine."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    intent: RequestIntent
    prompt: str
    context: SessionContext | None = None
    adapter_name: str
    options: dict[str, Any] = {}


class EngineResponse(BaseModel):
    """Immutable response object returned by the engine."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    content: str
    model_used: str | None = None
    usage: TokenUsage | None = None
    artifacts: list[FileArtifact] = []
    error: str | None = None


# Deferred import resolution for forward reference.
from auracode.models.context import SessionContext  # noqa: E402

EngineRequest.model_rebuild()
