"""Abstract base class for CI Provider Adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from auracode.ci.schemas import CiJobDefinition


class BaseCiAdapter(ABC):
    """Base adapter class for CI system integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name identifier."""
        ...

    @abstractmethod
    def detect(self, repo_path: str | Path) -> bool:
        """Returns True if this provider's configuration is present in the repository."""
        ...

    @abstractmethod
    def parse_workflows(self, repo_path: str | Path) -> list[CiJobDefinition]:
        """Parses and returns all active CI job definitions for this repository."""
        ...

    def supports_matrix(self) -> bool:
        """Returns True if matrix build expansion is supported."""
        return True
