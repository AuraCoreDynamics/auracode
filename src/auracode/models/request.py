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
    REFACTOR = "refactor"
    REVIEW_DIFF = "review_diff"
    SECURITY_REVIEW = "security_review"
    GENERATE_TESTS = "generate_tests"
    CROSS_FILE_EDIT = "cross_file_edit"
    ARCHITECTURE_TRACE = "architecture_trace"


class ExecutionMode(StrEnum):
    """How the engine should execute the request."""

    STANDARD = "standard"
    SPECULATIVE = "speculative"
    MONOLOGUE = "monologue"


class RoutingPreference(StrEnum):
    """Where the request should be routed."""

    AUTO = "auto"
    PREFER_LOCAL = "prefer_local"
    REQUIRE_LOCAL = "require_local"
    PREFER_GRID = "prefer_grid"
    REQUIRE_GRID = "require_grid"
    REQUIRE_VERIFIED = "require_verified"


class SovereigntyEnforcement(StrEnum):
    """How strictly sovereignty constraints are applied."""

    NONE = "none"
    WARN = "warn"
    ENFORCE = "enforce"


class RetrievalMode(StrEnum):
    """Whether retrieval augmentation is used."""

    DISABLED = "disabled"
    AUTO = "auto"
    REQUIRED = "required"


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


class SovereigntyPolicy(BaseModel):
    """Sovereignty constraints for a request."""

    model_config = ConfigDict(frozen=True)

    enforcement: SovereigntyEnforcement = SovereigntyEnforcement.NONE
    sensitivity_label: str | None = None
    audit_labels: list[str] = []
    allow_cloud: bool = True


class RetrievalPolicy(BaseModel):
    """Retrieval-augmented generation policy."""

    model_config = ConfigDict(frozen=True)

    mode: RetrievalMode = RetrievalMode.DISABLED
    require_citations: bool = False
    anchor_preferences: list[str] = []


class LatencyBudget(BaseModel):
    """Latency constraints for routing decisions."""

    model_config = ConfigDict(frozen=True)

    max_seconds: float | None = None
    prefer_fast: bool = False


class ExecutionPolicy(BaseModel):
    """Typed execution policy governing how a request is processed."""

    model_config = ConfigDict(frozen=True)

    mode: ExecutionMode = ExecutionMode.STANDARD
    routing: RoutingPreference = RoutingPreference.AUTO
    sovereignty: SovereigntyPolicy = SovereigntyPolicy()
    retrieval: RetrievalPolicy = RetrievalPolicy()
    latency: LatencyBudget = LatencyBudget()


class EngineRequest(BaseModel):
    """Immutable request object flowing into the engine."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    intent: RequestIntent
    prompt: str
    context: SessionContext | None = None
    adapter_name: str
    options: dict[str, Any] = {}
    execution_policy: ExecutionPolicy = ExecutionPolicy()


class DegradationNotice(BaseModel):
    """Records a capability that was downgraded during execution."""

    model_config = ConfigDict(frozen=True)

    capability: str
    requested: str
    actual: str
    reason: str = ""


class ExecutionMetadata(BaseModel):
    """Optional metadata about how the engine executed a request."""

    model_config = ConfigDict(frozen=True)

    analyzer_used: str | None = None
    execution_mode_used: ExecutionMode | None = None
    sovereignty_outcome: str | None = None
    retrieval_summary: str | None = None
    trace_id: str | None = None
    verification_outcome: str | None = None
    degradations: list[DegradationNotice] = []
    backend_warnings: list[str] = []


class EngineResponse(BaseModel):
    """Immutable response object returned by the engine."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    content: str
    model_used: str | None = None
    usage: TokenUsage | None = None
    artifacts: list[FileArtifact] = []
    error: str | None = None
    execution_metadata: ExecutionMetadata | None = None


# Deferred import resolution for forward reference.
from auracode.models.context import SessionContext  # noqa: E402

EngineRequest.model_rebuild()
