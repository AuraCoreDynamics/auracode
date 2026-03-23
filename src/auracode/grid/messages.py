"""Pure Python dataclasses mirroring the proto messages.

These allow the grid client to work without requiring grpcio or
protobuf compilation at runtime or test time.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class GridRequest:
    """Maps to ``auracode.grid.GridRequest`` proto message."""

    request_id: str = ""
    intent: str = ""
    prompt: str = ""
    context_json: str = ""
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class GridResponse:
    """Maps to ``auracode.grid.GridResponse`` proto message."""

    request_id: str = ""
    content: str = ""
    model_used: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""


@dataclass
class GridChunk:
    """Maps to ``auracode.grid.GridChunk`` proto message."""

    request_id: str = ""
    content_delta: str = ""
    is_final: bool = False


@dataclass
class Empty:
    """Maps to ``auracode.grid.Empty`` proto message."""


@dataclass
class HealthStatus:
    """Maps to ``auracode.grid.HealthStatus`` proto message."""

    healthy: bool = False
    version: str = ""


@dataclass
class ModelEntry:
    """Maps to ``auracode.grid.ModelEntry`` proto message."""

    model_id: str = ""
    provider: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ModelList:
    """Maps to ``auracode.grid.ModelList`` proto message."""

    models: list[ModelEntry] = field(default_factory=list)
