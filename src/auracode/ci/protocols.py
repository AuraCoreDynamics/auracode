"""Protocol contracts for AuraCode CI subsystem.

All protocols strictly adhere to structural subtyping (typing.Protocol)
with ellipsis (...) bodies to enforce abstract interface boundaries.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from auracode.ci.schemas import (
    CiDiagnosticEntry,
    CiJobDefinition,
    CiTaskRequest,
    CiTaskResult,
    RepairAttestation,
)


@runtime_checkable
class ICiProviderAdapter(Protocol):
    """Adapter interface for reading and translating CI workflow definitions."""

    @property
    def name(self) -> str: ...

    def detect(self, repo_path: str) -> bool: ...

    def parse_workflows(self, repo_path: str) -> list[CiJobDefinition]: ...

    def supports_matrix(self) -> bool: ...


@runtime_checkable
class IWorkflowParser(Protocol):
    """Workflow parser interface for translating workflow files into execution plans."""

    def parse_file(self, workflow_path: str) -> list[CiJobDefinition]: ...

    def expand_matrix(self, job: CiJobDefinition) -> list[CiJobDefinition]: ...


@runtime_checkable
class ICiConfigStore(Protocol):
    """Secure credential and configuration store backed by OS keyring."""

    def get_credential(self, service: str, account: str) -> str | None: ...

    def set_credential(self, service: str, account: str, secret: str) -> bool: ...

    def delete_credential(self, service: str, account: str) -> bool: ...


@runtime_checkable
class ICiRunner(Protocol):
    """Dispatches CI task requests to local containers or the AuraGrid auction mesh."""

    def execute_job(self, request: CiTaskRequest) -> CiTaskResult: ...


@runtime_checkable
class IDiagnosticExtractor(Protocol):
    """Parses untrusted logs and extracts structured, categorized error diagnostics."""

    def extract(self, log_content: str) -> list[CiDiagnosticEntry]: ...


@runtime_checkable
class IRepairEngine(Protocol):
    """Orchestrates bounded, closed-loop code repair on isolated worktrees."""

    def attempt_repair(
        self,
        repo_path: str,
        commit_sha: str,
        diagnostics: list[CiDiagnosticEntry],
        max_iterations: int = 3,
    ) -> RepairAttestation | None: ...
