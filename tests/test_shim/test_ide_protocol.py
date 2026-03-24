"""Tests for IDE wire protocol Pydantic models."""

from __future__ import annotations

import json

import pytest

from auracode.shim.ide_protocol import (
    CancelRequest,
    ChatMessage,
    Diagnostic,
    FileSnapshot,
    IdeContext,
    ServerError,
    StatusUpdate,
    StreamEnd,
    StreamToken,
    TextSelection,
    ToolRequest,
    ToolResponse,
)

# ── Round-trip serialization ──────────────────────────────────────────


class TestClientModels:
    """Client → Server models serialize and deserialize correctly."""

    def test_text_selection_round_trip(self):
        sel = TextSelection(start_line=1, start_col=0, end_line=1, end_col=10, text="hello")
        data = json.loads(sel.model_dump_json())
        restored = TextSelection.model_validate(data)
        assert restored == sel
        assert restored.text == "hello"

    def test_diagnostic_round_trip(self):
        diag = Diagnostic(
            file_path="main.py",
            line=42,
            col=5,
            severity="warning",
            message="Unused import",
            source="ruff",
        )
        data = json.loads(diag.model_dump_json())
        restored = Diagnostic.model_validate(data)
        assert restored == diag
        assert restored.severity == "warning"

    def test_file_snapshot_with_nested(self):
        snap = FileSnapshot(
            path="src/app.py",
            content="print('hi')",
            language="python",
            version=3,
            selection=TextSelection(start_line=1, start_col=0, end_line=1, end_col=5),
            diagnostics=[
                Diagnostic(file_path="src/app.py", line=1, col=0, message="test"),
            ],
        )
        data = json.loads(snap.model_dump_json())
        restored = FileSnapshot.model_validate(data)
        assert restored.selection is not None
        assert restored.selection.start_line == 1
        assert len(restored.diagnostics) == 1

    def test_ide_context_defaults(self):
        ctx = IdeContext()
        assert ctx.workspace_root == "."
        assert ctx.open_files == []
        assert ctx.metadata == {}

    def test_chat_message_minimal(self):
        msg = ChatMessage(message="Hello")
        assert msg.type == "chat"
        assert msg.session_id is None
        data = json.loads(msg.model_dump_json())
        assert data["type"] == "chat"
        assert data["message"] == "Hello"

    def test_chat_message_full(self):
        msg = ChatMessage(
            message="Fix this bug",
            session_id="abc123",
            intent="edit_code",
            ide_context=IdeContext(
                workspace_root="/home/user/project",
                active_file="main.py",
            ),
        )
        data = json.loads(msg.model_dump_json())
        restored = ChatMessage.model_validate(data)
        assert restored.session_id == "abc123"
        assert restored.ide_context is not None
        assert restored.ide_context.workspace_root == "/home/user/project"

    def test_cancel_request(self):
        req = CancelRequest(request_id="req-001")
        assert req.type == "cancel"
        data = json.loads(req.model_dump_json())
        restored = CancelRequest.model_validate(data)
        assert restored.request_id == "req-001"

    def test_tool_response_approved(self):
        resp = ToolResponse(request_id="tool-001", approved=True, result="file written")
        data = json.loads(resp.model_dump_json())
        assert data["type"] == "tool_response"
        restored = ToolResponse.model_validate(data)
        assert restored.approved is True
        assert restored.result == "file written"

    def test_tool_response_denied(self):
        resp = ToolResponse(request_id="tool-002", approved=False, error="User denied")
        assert resp.approved is False
        assert resp.error == "User denied"


class TestServerModels:
    """Server → Client models serialize and deserialize correctly."""

    def test_stream_token(self):
        tok = StreamToken(request_id="r1", content="Hello", model_used="gpt-4")
        data = json.loads(tok.model_dump_json())
        assert data["type"] == "token"
        restored = StreamToken.model_validate(data)
        assert restored.content == "Hello"
        assert restored.model_used == "gpt-4"

    def test_stream_end(self):
        end = StreamEnd(
            request_id="r1",
            model_used="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
        )
        data = json.loads(end.model_dump_json())
        assert data["type"] == "end"
        assert data["prompt_tokens"] == 100

    def test_tool_request(self):
        req = ToolRequest(
            request_id="t1",
            tool="file_write",
            params={"path": "out.py", "content": "x = 1"},
            description="Write output file",
        )
        data = json.loads(req.model_dump_json())
        assert data["tool"] == "file_write"
        restored = ToolRequest.model_validate(data)
        assert restored.params["path"] == "out.py"

    def test_tool_request_all_types(self):
        for tool in ("file_write", "file_read", "terminal_exec", "search"):
            req = ToolRequest(request_id="t", tool=tool)
            assert req.tool == tool

    def test_server_error(self):
        err = ServerError(request_id="r1", message="boom", code="stream_error")
        data = json.loads(err.model_dump_json())
        assert data["type"] == "error"
        restored = ServerError.model_validate(data)
        assert restored.message == "boom"

    def test_server_error_no_request_id(self):
        err = ServerError(message="bad request")
        assert err.request_id is None
        assert err.code == "internal_error"

    def test_status_update(self):
        status = StatusUpdate(
            request_id="r1",
            message="Working...",
            phase="streaming",
        )
        data = json.loads(status.model_dump_json())
        assert data["type"] == "status"
        restored = StatusUpdate.model_validate(data)
        assert restored.phase == "streaming"


class TestModelImmutability:
    """All protocol models are frozen."""

    def test_chat_message_frozen(self):
        msg = ChatMessage(message="hi")
        with pytest.raises(Exception):
            msg.message = "changed"

    def test_stream_token_frozen(self):
        tok = StreamToken(request_id="r", content="x")
        with pytest.raises(Exception):
            tok.content = "y"

    def test_server_error_frozen(self):
        err = ServerError(message="x")
        with pytest.raises(Exception):
            err.message = "y"
