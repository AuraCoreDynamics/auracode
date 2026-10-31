"""Immutable schemas for AuraCode grid CI/CD."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

_ENV_KEY_REGEX = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_DIGEST_REGEX = re.compile(r"^(?:[a-zA-Z0-9_.\-\/]+@)?sha256:[a-f0-9]{64}$")


class CiJobPriority(StrEnum):
    """Execution priority for CI/CD jobs within the grid auction and node scheduler."""

    PRE_PUSH_GATE = "PrePushGate"
    ROUTINE = "Routine"


class CiTaskStatus(StrEnum):
    """Status outcome of a CI task execution."""

    PASSED = "Passed"
    FAILED = "Failed"
    TIMED_OUT = "TimedOut"
    REJECTED = "Rejected"
    INFRA_ERROR = "InfraError"
    CANCELLED = "Cancelled"


class CiExecutionMode(StrEnum):
    """Execution mode for CI/CD tasks. Native host execution is strictly banned."""

    WRAPPED_CONTAINER = "WrappedContainer"


@dataclass(frozen=True)
class CiWorkspaceRef:
    """Immutable workspace reference pointing to the exact git commit tree and archived bundle."""

    commit_sha: str
    tree_hash: str
    bundle_uri: str
    bundle_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiWorkspaceRef:
        return cls(
            commit_sha=data["commit_sha"],
            tree_hash=data["tree_hash"],
            bundle_uri=data["bundle_uri"],
            bundle_sha256=data["bundle_sha256"],
        )


@dataclass(frozen=True)
class CiStep:
    """Atomic build or test step within a CI job."""

    name: str
    run: str
    shell: str = "bash"
    timeout_sec: int = 300
    if_expr: str | None = None
    continue_on_error: bool = False
    working_directory: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiStep:
        return cls(
            name=data["name"],
            run=data["run"],
            shell=data.get("shell", "bash"),
            timeout_sec=int(data.get("timeout_sec", 300)),
            if_expr=data.get("if_expr"),
            continue_on_error=bool(data.get("continue_on_error", False)),
            working_directory=data.get("working_directory"),
            env=dict(data.get("env", {})),
            id=data.get("id"),
        )


@dataclass(frozen=True)
class CiStepResult:
    """Execution outcome of an individual step within a CI job."""

    name: str
    exit_code: int
    duration_ms: int
    stdout_excerpt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiStepResult:
        return cls(
            name=data["name"],
            exit_code=int(data["exit_code"]),
            duration_ms=int(data["duration_ms"]),
            stdout_excerpt=data.get("stdout_excerpt"),
        )


@dataclass(frozen=True)
class CiResourceLimits:
    """EP-004 resource constraints enforced via OS cgroups and container engine flags."""

    max_memory_mb: int = 2048
    cpu_threads: int = 2
    pids_limit: int = 512
    timeout_sec: int = 600

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiResourceLimits:
        return cls(
            max_memory_mb=int(data.get("max_memory_mb", 2048)),
            cpu_threads=int(data.get("cpu_threads", 2)),
            pids_limit=int(data.get("pids_limit", 512)),
            timeout_sec=int(data.get("timeout_sec", 600)),
        )


@dataclass(frozen=True)
class CiTaskRequest:
    """Dispatch contract submitted to the grid auction for CI/CD execution."""

    job_id: str
    workspace_ref: CiWorkspaceRef
    image_digest: str
    steps: list[CiStep]
    environment: dict[str, str] = field(default_factory=dict)
    resource_limits: CiResourceLimits = field(default_factory=CiResourceLimits)
    priority: CiJobPriority = CiJobPriority.ROUTINE
    idempotency_key: str = ""
    job_key: str = ""

    def __post_init__(self) -> None:
        if not _DIGEST_REGEX.match(self.image_digest):
            msg = (
                f"Image digest '{self.image_digest}' must be a pinned sha256 hash "
                "(format: sha256:<64-hex> or repo@sha256:<64-hex>)"
            )
            raise ValueError(msg)
        for key in self.environment:
            if not _ENV_KEY_REGEX.match(key):
                msg = (
                    f"Environment key '{key}' violates POSIX shell standard "
                    "(must match ^[A-Z_][A-Z0-9_]*$)"
                )
                raise ValueError(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "workspace_ref": self.workspace_ref.to_dict(),
            "image_digest": self.image_digest,
            "steps": [s.to_dict() for s in self.steps],
            "environment": dict(self.environment),
            "resource_limits": self.resource_limits.to_dict(),
            "priority": self.priority.value,
            "idempotency_key": self.idempotency_key,
            "job_key": self.job_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiTaskRequest:
        return cls(
            job_id=data["job_id"],
            workspace_ref=CiWorkspaceRef.from_dict(data["workspace_ref"]),
            image_digest=data["image_digest"],
            steps=[CiStep.from_dict(s) for s in data.get("steps", [])],
            environment=dict(data.get("environment", {})),
            resource_limits=CiResourceLimits.from_dict(data.get("resource_limits", {})),
            priority=CiJobPriority(data.get("priority", CiJobPriority.ROUTINE.value)),
            idempotency_key=data.get("idempotency_key", ""),
            job_key=data.get("job_key", ""),
        )


@dataclass(frozen=True)
class CiTaskResult:
    """Attested result from a sandboxed container CI execution on a grid node."""

    job_id: str
    exit_code: int
    execution_mode: CiExecutionMode
    duration_ms: int
    fencing_token: int
    node_id: str
    node_signature: str
    stdout_sha256: str
    status: CiTaskStatus = CiTaskStatus.PASSED
    truncated: bool = False
    failed_step_name: str | None = None
    diagnostic_summary: str | None = None
    step_results: list[CiStepResult] = field(default_factory=list)
    tree_hash: str = ""
    image_digest: str = ""
    idempotency_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "exit_code": self.exit_code,
            "execution_mode": self.execution_mode.value,
            "duration_ms": self.duration_ms,
            "fencing_token": self.fencing_token,
            "node_id": self.node_id,
            "node_signature": self.node_signature,
            "stdout_sha256": self.stdout_sha256,
            "truncated": self.truncated,
            "failed_step_name": self.failed_step_name,
            "diagnostic_summary": self.diagnostic_summary,
            "step_results": [s.to_dict() for s in self.step_results],
            "tree_hash": self.tree_hash,
            "image_digest": self.image_digest,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiTaskResult:
        status_val = data.get("status")
        if status_val:
            status = CiTaskStatus(status_val)
        else:
            status = (
                CiTaskStatus.PASSED if int(data.get("exit_code", 0)) == 0 else CiTaskStatus.FAILED
            )

        return cls(
            job_id=data["job_id"],
            status=status,
            exit_code=int(data["exit_code"]),
            execution_mode=CiExecutionMode(
                data.get("execution_mode", CiExecutionMode.WRAPPED_CONTAINER.value)
            ),
            duration_ms=int(data["duration_ms"]),
            fencing_token=int(data["fencing_token"]),
            node_id=data["node_id"],
            node_signature=data["node_signature"],
            stdout_sha256=data["stdout_sha256"],
            truncated=bool(data.get("truncated", False)),
            failed_step_name=data.get("failed_step_name"),
            diagnostic_summary=data.get("diagnostic_summary"),
            step_results=[CiStepResult.from_dict(s) for s in data.get("step_results", [])],
            tree_hash=data.get("tree_hash", ""),
            image_digest=data.get("image_digest", ""),
            idempotency_key=data.get("idempotency_key", ""),
        )


@dataclass(frozen=True)
class CiJobDefinition:
    """Parsed job specification from CI workflow file."""

    name: str
    runs_on: str
    steps: list[CiStep]
    environment: dict[str, str] = field(default_factory=dict)
    matrix: dict[str, list[Any]] = field(default_factory=dict)
    job_key: str = ""
    needs: list[str] = field(default_factory=list)
    requires_secrets: bool = False
    image_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "runs_on": self.runs_on,
            "steps": [s.to_dict() for s in self.steps],
            "environment": dict(self.environment),
            "matrix": dict(self.matrix),
            "job_key": self.job_key,
            "needs": list(self.needs),
            "requires_secrets": self.requires_secrets,
            "image_digest": self.image_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiJobDefinition:
        return cls(
            name=data["name"],
            runs_on=data.get("runs_on", "ubuntu-latest"),
            steps=[CiStep.from_dict(s) for s in data.get("steps", [])],
            environment=dict(data.get("environment", {})),
            matrix=dict(data.get("matrix", {})),
            job_key=data.get("job_key", ""),
            needs=list(data.get("needs", [])),
            requires_secrets=bool(data.get("requires_secrets", False)),
            image_digest=data.get("image_digest", ""),
        )


@dataclass(frozen=True)
class CiDiagnosticEntry:
    """Normalized diagnostic entry extracted from build or test logs."""

    file: str | None
    line: int | None
    rule_id: str | None
    message: str
    category: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CiDiagnosticEntry:
        return cls(
            file=data.get("file"),
            line=data.get("line"),
            rule_id=data.get("rule_id"),
            message=data.get("message", ""),
            category=data.get("category", "error"),
        )


@dataclass(frozen=True)
class RepairAttestation:
    """Cryptographic and fencing attestation for an autonomous repair operation."""

    job_id: str
    source_sha: str
    repaired_sha: str
    iteration_count: int
    fencing_token: int
    repaired_by_node_id: str
    signature: str
    model: str = ""
    prompt_sha256: str = ""
    verified_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepairAttestation:
        return cls(
            job_id=data["job_id"],
            source_sha=data["source_sha"],
            repaired_sha=data["repaired_sha"],
            iteration_count=int(data["iteration_count"]),
            fencing_token=int(data["fencing_token"]),
            repaired_by_node_id=data["repaired_by_node_id"],
            signature=data["signature"],
            model=data.get("model", ""),
            prompt_sha256=data.get("prompt_sha256", ""),
            verified_by=data.get("verified_by", ""),
        )
