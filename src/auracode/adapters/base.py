"""Abstract base class for adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import click

from auracode.models.request import EngineRequest, EngineResponse


class BaseAdapter(ABC):
    """Adapter ABC — bridges an external interface (CLI, IDE, MCP) to the engine."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this adapter."""
        ...

    @abstractmethod
    async def translate_request(self, raw_input: Any) -> EngineRequest:
        """Convert adapter-specific input into an EngineRequest."""
        ...

    @abstractmethod
    async def translate_response(self, response: EngineResponse) -> Any:
        """Convert an EngineResponse into adapter-specific output."""
        ...

    @abstractmethod
    def get_cli_group(self) -> click.Group | None:
        """Return a Click group to mount under the root CLI, or None."""
        ...
