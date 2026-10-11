"""Verification and remediation domain models for the autonomous agent loop."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from auracode.models.request import EngineResponse


class VerificationCommand(BaseModel):
    """Configuration for a local verification command (test suite, linter, compiler)."""

    model_config = ConfigDict(frozen=True)

    command: str
    timeout_seconds: int = 60
    working_directory: str = "."


class VerificationResult(BaseModel):
    """Execution outcome of a verification command."""

    model_config = ConfigDict(frozen=True)

    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool
    duration_ms: int


class RemediationBudget(BaseModel):
    """Tracks remediation attempts for self-healing loops."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = 3
    current_attempt: int = 0


class RemediationStep(BaseModel):
    """A single remediation step within an agent loop."""

    model_config = ConfigDict(frozen=True)

    attempt: int
    verification: VerificationResult
    diagnosis: str | None = None


class AgentLoopResult(BaseModel):
    """Result of an autonomous self-healing agent loop execution."""

    model_config = ConfigDict(frozen=True)

    status: str  # "success" | "remediation_exhausted" | "permission_denied" | "error"
    final_response: EngineResponse | None = None
    remediations: list[RemediationStep] = Field(default_factory=list)
    snapshot_id: str | None = None
    rollback_available: bool = False


AgentLoopResult.model_rebuild()
