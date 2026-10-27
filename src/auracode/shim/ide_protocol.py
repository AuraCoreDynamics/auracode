"""IDE wire protocol — Pydantic models for WebSocket message types."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# ── Client → Server ──────────────────────────────────────────────────────


class TextSelection(BaseModel):
    """A text selection range within a file."""

    model_config = ConfigDict(frozen=True)

    start_line: int
    start_col: int
    end_line: int
    end_col: int
    text: str = ""


class Diagnostic(BaseModel):
    """A single diagnostic (error/warning) from the IDE."""

    model_config = ConfigDict(frozen=True)

    file_path: str
    line: int
    col: int
    severity: Literal["error", "warning", "info", "hint"] = "error"
    message: str = ""
    source: str = ""


class FileSnapshot(BaseModel):
    """Snapshot of a file currently open in the IDE."""

    model_config = ConfigDict(frozen=True)

    path: str
    content: str | None = None
    language: str | None = None
    version: int = 0
    selection: TextSelection | None = None
    diagnostics: list[Diagnostic] = []


class IdeContext(BaseModel):
    """Full IDE context attached to a chat message."""

    model_config = ConfigDict(frozen=True)

    workspace_root: str = "."
    active_file: str | None = None
    open_files: list[FileSnapshot] = []
    terminal_output: str | None = None
    metadata: dict[str, Any] = {}


class ChatMessage(BaseModel):
    """A chat message from the IDE user."""

    model_config = ConfigDict(frozen=True)

    type: Literal["chat"] = "chat"
    message: str
    session_id: str | None = None
    intent: str | None = None
    ide_context: IdeContext | None = None


class CancelRequest(BaseModel):
    """Request to cancel an in-progress generation."""

    model_config = ConfigDict(frozen=True)

    type: Literal["cancel"] = "cancel"
    request_id: str


class ToolResponse(BaseModel):
    """Response to a tool request from the server."""

    model_config = ConfigDict(frozen=True)

    type: Literal["tool_response"] = "tool_response"
    request_id: str
    approved: bool = True
    result: str = ""
    error: str | None = None


# ── Server → Client ──────────────────────────────────────────────────────


class StreamToken(BaseModel):
    """A single token (or chunk) of streaming output."""

    model_config = ConfigDict(frozen=True)

    type: Literal["token"] = "token"
    request_id: str
    content: str
    model_used: str | None = None


class StreamEnd(BaseModel):
    """Marks the end of a streaming response."""

    model_config = ConfigDict(frozen=True)

    type: Literal["end"] = "end"
    request_id: str
    model_used: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    aura_routing_context: dict[str, Any] | None = None


class ToolRequest(BaseModel):
    """Server requesting the IDE to execute a tool (requires confirmation)."""

    model_config = ConfigDict(frozen=True)

    type: Literal["tool_request"] = "tool_request"
    request_id: str
    tool: Literal["file_write", "file_read", "terminal_exec", "search"]
    params: dict[str, Any] = {}
    description: str = ""


class ServerError(BaseModel):
    """An error from the server."""

    model_config = ConfigDict(frozen=True)

    type: Literal["error"] = "error"
    request_id: str | None = None
    message: str
    code: str = "internal_error"


class StatusUpdate(BaseModel):
    """A status update from the server (informational)."""

    model_config = ConfigDict(frozen=True)

    type: Literal["status"] = "status"
    request_id: str | None = None
    message: str
    phase: str = ""


# ── IDE Protocol V2 Extensions ──────────────────────────────────────────


class ActRequest(BaseModel):
    """Client request to invoke autonomous self-healing execution loop."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.act_request", "act"] = "ide.act_request"
    prompt: str
    verify_command: str | None = None
    max_attempts: int = 3
    workspace: str = "."


class ActProgress(BaseModel):
    """Server streaming progress of self-healing execution loop."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.act_progress"] = "ide.act_progress"
    status: str
    phase: str = "running"
    attempt: int = 0


class ActCompleted(BaseModel):
    """Server completion payload for self-healing execution loop."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.act_completed"] = "ide.act_completed"
    status: str
    snapshot_id: str | None = None
    remediations_count: int = 0
    output: str = ""


class ResolveConflictRequest(BaseModel):
    """Client request to resolve 3-way merge conflict in a file."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.resolve_conflict_request", "resolve_conflict"] = (
        "ide.resolve_conflict_request"
    )
    file_path: str
    workspace: str = "."


class ConflictsDetected(BaseModel):
    """Server notification of active Git merge conflict blocks in workspace."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.conflicts_detected"] = "ide.conflicts_detected"
    count: int
    files: list[str] = []


class RepoMapRequest(BaseModel):
    """Client request for structural AST repo-map."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.repomap_request", "repomap"] = "ide.repomap_request"
    workspace_root: str = "."
    max_chars: int = 2048


class RepoMapResponse(BaseModel):
    """Server response containing structural AST repo-map."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.repomap_response"] = "ide.repomap_response"
    workspace_root: str
    map_text: str
    symbol_count: int = 0


# ── Bidirectional IDE Diagnostics & Buffer Protocol ──────────────────────


class DiagnosticsUpdate(BaseModel):
    """Notification of updated IDE diagnostics from connected IDE."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.diagnostics_update", "diagnostics_update"] = "ide.diagnostics_update"
    file_path: str | None = None
    diagnostics: list[Diagnostic] = []


class BufferUpdate(BaseModel):
    """Notification of active or updated file buffer from connected IDE."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.buffer_update", "buffer_update"] = "ide.buffer_update"
    file_path: str
    content: str
    language: str | None = None
    is_dirty: bool = False
    selection: TextSelection | None = None


class DiagnosticsRequest(BaseModel):
    """Server request asking IDE for active diagnostics."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.diagnostics_request"] = "ide.diagnostics_request"
    request_id: str
    file_path: str | None = None


class DiagnosticsResponse(BaseModel):
    """Client response containing active diagnostics."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.diagnostics_response"] = "ide.diagnostics_response"
    request_id: str
    diagnostics: list[Diagnostic] = []


class ActiveBufferRequest(BaseModel):
    """Server request asking IDE for active buffer content."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.active_buffer_request"] = "ide.active_buffer_request"
    request_id: str


class ActiveBufferResponse(BaseModel):
    """Client response containing active buffer."""

    model_config = ConfigDict(frozen=True)

    type: Literal["ide.active_buffer_response"] = "ide.active_buffer_response"
    request_id: str
    active_file: str | None = None
    content: str | None = None
    language: str | None = None
    selection: TextSelection | None = None
