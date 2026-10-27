"""Tests for IdeStateStore and bidirectional IDE MCP tools."""

from __future__ import annotations

import pytest

from auracode.shim.ide_protocol import Diagnostic, FileSnapshot, IdeContext, TextSelection
from auracode.shim.ide_state import IdeStateStore


def test_ide_state_store_basics():
    store = IdeStateStore()
    assert store.get_active_buffer() is None
    assert store.get_diagnostics() == []
    assert not store.has_errors()

    # Update active buffer
    store.update_buffer(
        "src/main.py",
        "print('hello world')",
        language="python",
        selection=TextSelection(start_line=1, start_col=0, end_line=1, end_col=5, text="print"),
    )

    buf = store.get_active_buffer()
    assert buf is not None
    assert buf["path"] == "src/main.py"
    assert buf["language"] == "python"
    assert "hello world" in buf["content"]
    assert buf["selection"]["text"] == "print"

    # Add diagnostics
    store.update_diagnostics(
        "src/main.py",
        [
            Diagnostic(
                file_path="src/main.py",
                line=1,
                col=0,
                severity="error",
                message="Undefined variable 'print'",
            ),
            Diagnostic(
                file_path="src/main.py", line=1, col=6, severity="warning", message="Unused import"
            ),
        ],
    )

    assert store.has_errors()
    assert store.has_errors("src/main.py")
    assert not store.has_errors("src/other.py")

    errors = store.get_diagnostics(severity="error")
    assert len(errors) == 1
    assert errors[0].message == "Undefined variable 'print'"

    warnings = store.get_diagnostics(severity="warning")
    assert len(warnings) == 1


def test_ide_state_store_update_from_context():
    store = IdeStateStore()
    context = IdeContext(
        workspace_root="/home/user/project",
        active_file="app.py",
        open_files=[
            FileSnapshot(
                path="app.py",
                content="import os\n",
                language="python",
                diagnostics=[
                    Diagnostic(
                        file_path="app.py",
                        line=1,
                        col=7,
                        severity="error",
                        message="Module not found",
                    ),
                ],
            ),
            FileSnapshot(
                path="README.md",
                content="# Docs\n",
                language="markdown",
            ),
        ],
    )

    store.update_from_context(context)
    assert store.workspace_root == "/home/user/project"
    assert store.active_file == "app.py"
    assert store.has_errors("app.py")

    buf = store.get_active_buffer()
    assert buf is not None
    assert buf["path"] == "app.py"

    open_bufs = store.get_open_buffers()
    assert len(open_bufs) == 2


@pytest.mark.asyncio
async def test_mcp_ide_tools(monkeypatch, tmp_path):
    from auracode.mcp_server import create_mcp_server
    from auracode.shim.ide_state import ide_state

    ide_state.clear()
    ide_state.update_buffer("src/App.cs", "class App {}", language="csharp")
    ide_state.update_diagnostics(
        "src/App.cs",
        [
            Diagnostic(
                file_path="src/App.cs",
                line=1,
                col=6,
                severity="error",
                message="Type expected",
                source="Roslyn",
            ),
        ],
    )

    class DummyEngine:
        config = type(
            "Config",
            (),
            {
                "working_directory": ".",
                "permissions": type("Perms", (), {"allow_file_write": False})(),
            },
        )()

    server = create_mcp_server(DummyEngine())
    if server is None:
        pytest.skip("mcp package not installed")

    # Call tools through FastMCP tool registry
    # FastMCP stores tools in server._tool_manager or provides call_tool
    tool_names = [t.name for t in await server.list_tools()]
    assert "auracode_ide_get_diagnostics" in tool_names
    assert "auracode_ide_get_active_buffer" in tool_names
    assert "auracode_ide_get_open_buffers" in tool_names
    assert "auragrid_app_init" in tool_names

    # Direct invocation
    diag_text = await server.call_tool("auracode_ide_get_diagnostics", {})
    # FastMCP call_tool returns list of content or text
    diag_str = str(diag_text)
    assert "Type expected" in diag_str
    assert "Roslyn" in diag_str

    buf_res = await server.call_tool("auracode_ide_get_active_buffer", {})
    buf_str = str(buf_res)
    assert "src/App.cs" in buf_str
    assert "class App {}" in buf_str

    target_app_dir = tmp_path / "tmp_mcp_app"
    init_res = await server.call_tool(
        "auragrid_app_init",
        {
            "name": "mcp-beacon-app",
            "template": "tier4",
            "target_dir": str(target_app_dir),
        },
    )
    assert "tmp_mcp_app" in str(init_res) or "success" in str(init_res)
    assert (target_app_dir / "app.manifest.json").exists()
