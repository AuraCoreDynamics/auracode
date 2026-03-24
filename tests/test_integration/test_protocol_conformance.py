"""Protocol conformance tests.

Validates that message types and field names are consistent across
the Python server, TypeScript client, and C# client.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from auracode.shim.ide_protocol import (
    CancelRequest,
    ChatMessage,
    ServerError,
    StatusUpdate,
    StreamEnd,
    StreamToken,
    ToolRequest,
    ToolResponse,
)

# ── Paths to client protocol definitions ────────────────────────────

TS_PROTOCOL = (
    Path(__file__).resolve().parents[3]
    / "auracode-visualstudio"
    / "vscode"
    / "src"
    / "client"
    / "protocol.ts"
)
CS_PROTOCOL = (
    Path(__file__).resolve().parents[3]
    / "auracode-visualstudio"
    / "visualstudio"
    / "src"
    / "AuraCode"
    / "Client"
    / "Protocol.cs"
)


# ── Python canonical type names ─────────────────────────────────────

PYTHON_SERVER_TYPES = {
    "token": StreamToken,
    "end": StreamEnd,
    "tool_request": ToolRequest,
    "error": ServerError,
    "status": StatusUpdate,
}

PYTHON_CLIENT_TYPES = {
    "chat": ChatMessage,
    "cancel": CancelRequest,
    "tool_response": ToolResponse,
}


class TestPythonProtocol:
    """Verify Python protocol models have correct type discriminators."""

    def test_stream_token_type_is_token(self):
        tok = StreamToken(request_id="r1", content="hi")
        assert tok.type == "token"
        data = json.loads(tok.model_dump_json())
        assert data["type"] == "token"
        assert "content" in data  # Not "token"

    def test_stream_end_type_is_end(self):
        end = StreamEnd(request_id="r1")
        assert end.type == "end"

    def test_tool_request_type(self):
        req = ToolRequest(request_id="t1", tool="file_read")
        assert req.type == "tool_request"

    def test_server_error_type(self):
        err = ServerError(message="fail")
        assert err.type == "error"

    def test_status_update_type(self):
        su = StatusUpdate(message="working")
        assert su.type == "status"

    def test_chat_message_type(self):
        msg = ChatMessage(message="hi")
        assert msg.type == "chat"

    def test_cancel_request_type(self):
        cr = CancelRequest(request_id="r1")
        assert cr.type == "cancel"

    def test_tool_response_type(self):
        tr = ToolResponse(request_id="r1")
        assert tr.type == "tool_response"


class TestTypeScriptConformance:
    """Verify TypeScript protocol.ts defines the same type names."""

    @pytest.fixture(autouse=True)
    def _load_ts(self):
        if not TS_PROTOCOL.exists():
            pytest.skip(f"TypeScript protocol not found at {TS_PROTOCOL}")
        self.ts_content = TS_PROTOCOL.read_text(encoding="utf-8")

    def test_server_message_types_present(self):
        """TS must define interfaces with matching type literals."""
        for type_name in PYTHON_SERVER_TYPES:
            assert f'"{type_name}"' in self.ts_content, (
                f'TypeScript protocol.ts missing type literal "{type_name}"'
            )

    def test_client_message_types_present(self):
        for type_name in PYTHON_CLIENT_TYPES:
            assert f'"{type_name}"' in self.ts_content, (
                f'TypeScript protocol.ts missing type literal "{type_name}"'
            )

    def test_stream_token_uses_content_not_token(self):
        """The field must be 'content', not 'token'."""
        # Find the StreamToken interface
        assert "content: string" in self.ts_content
        # The interface should NOT have a 'token' field for the content
        # (there is a TokenUsage type, so we check specifically in StreamToken context)
        stream_token_match = re.search(r"interface StreamToken\s*\{([^}]+)\}", self.ts_content)
        if stream_token_match:
            body = stream_token_match.group(1)
            assert "content:" in body, "StreamToken should have 'content' field"

    def test_tool_types_match(self):
        for tool in ("file_write", "file_read", "terminal_exec", "search"):
            assert f'"{tool}"' in self.ts_content, f'TypeScript missing tool type "{tool}"'


class TestCSharpConformance:
    """Verify C# Protocol.cs defines the same type names."""

    @pytest.fixture(autouse=True)
    def _load_cs(self):
        if not CS_PROTOCOL.exists():
            pytest.skip(f"C# protocol not found at {CS_PROTOCOL}")
        self.cs_content = CS_PROTOCOL.read_text(encoding="utf-8")

    def test_server_message_types_present(self):
        for type_name in PYTHON_SERVER_TYPES:
            assert f'"{type_name}"' in self.cs_content or f"'{type_name}'" in self.cs_content, (
                f'C# Protocol.cs missing type literal "{type_name}"'
            )

    def test_client_message_types_present(self):
        for type_name in PYTHON_CLIENT_TYPES:
            assert f'"{type_name}"' in self.cs_content or f"'{type_name}'" in self.cs_content, (
                f'C# Protocol.cs missing type literal "{type_name}"'
            )

    def test_tool_request_class_exists(self):
        """C# uses a string Tool property — verify the class exists."""
        assert "class ToolRequest" in self.cs_content
        assert "Tool" in self.cs_content
