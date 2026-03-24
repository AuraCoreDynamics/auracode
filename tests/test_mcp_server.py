"""Tests for mcp_server.py — MCP tool exposure of AuraCode capabilities."""

from __future__ import annotations

import sys
import types
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auracode.models.request import EngineResponse, RequestIntent, TokenUsage
from auracode.routing.base import ModelInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_engine(
    response_content: str = "generated output",
    response_error: str | None = None,
    models: list[ModelInfo] | None = None,
) -> MagicMock:
    """Build a mock engine whose execute() returns a predictable EngineResponse."""
    engine = MagicMock()
    engine.execute = AsyncMock(
        return_value=EngineResponse(
            request_id="test-resp",
            content=response_content,
            model_used="mock-v1",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
            error=response_error or "",
        )
    )
    engine.router = MagicMock()
    engine.router.list_models = AsyncMock(return_value=models or [])
    return engine


# ---------------------------------------------------------------------------
# Tests: create_mcp_server availability
# ---------------------------------------------------------------------------


class TestCreateMcpServer:
    def test_returns_none_when_mcp_not_installed(self) -> None:
        """When 'mcp' package is missing, create_mcp_server returns None."""
        from auracode import mcp_server

        saved = sys.modules.get("mcp")
        saved_srv = sys.modules.get("mcp.server")
        # Force ImportError by poisoning the module cache
        sys.modules["mcp"] = None  # type: ignore[assignment]
        sys.modules["mcp.server"] = None  # type: ignore[assignment]
        try:
            # Re-import to pick up the change
            result = mcp_server.create_mcp_server(engine=MagicMock())
            assert result is None
        finally:
            if saved is not None:
                sys.modules["mcp"] = saved
            else:
                sys.modules.pop("mcp", None)
            if saved_srv is not None:
                sys.modules["mcp.server"] = saved_srv
            else:
                sys.modules.pop("mcp.server", None)

    def test_returns_server_when_mcp_available(self) -> None:
        """When mcp package IS available, create_mcp_server returns a server object."""
        # Create a fake mcp.server module with FastMCP
        fake_server_cls = MagicMock()
        fake_server_instance = MagicMock()
        fake_server_instance.tool.return_value = lambda fn: fn  # decorator passthrough
        fake_server_cls.return_value = fake_server_instance

        fake_mcp = types.ModuleType("mcp")
        fake_mcp_server = types.ModuleType("mcp.server")
        fake_mcp_server.FastMCP = fake_server_cls  # type: ignore[attr-defined]

        saved = sys.modules.get("mcp")
        saved_srv = sys.modules.get("mcp.server")
        sys.modules["mcp"] = fake_mcp
        sys.modules["mcp.server"] = fake_mcp_server
        try:
            from auracode.mcp_server import create_mcp_server

            result = create_mcp_server(engine=MagicMock())
            assert result is fake_server_instance
            # FastMCP was called with "auracode"
            fake_server_cls.assert_called_once_with("auracode")
        finally:
            if saved is not None:
                sys.modules["mcp"] = saved
            else:
                sys.modules.pop("mcp", None)
            if saved_srv is not None:
                sys.modules["mcp.server"] = saved_srv
            else:
                sys.modules.pop("mcp.server", None)


# ---------------------------------------------------------------------------
# Tests: MCP tool functions (invoked as regular async functions)
# ---------------------------------------------------------------------------


class TestMcpTools:
    """Test the tool functions by extracting them from a mock FastMCP server."""

    @pytest.fixture()
    def tools_and_engine(self) -> tuple[dict[str, Any], MagicMock]:
        """Set up a fake mcp module, call create_mcp_server, and capture registered tools."""
        registered_tools: dict[str, Any] = {}

        class FakeFastMCP:
            def __init__(self, name: str):
                self._name = name

            def tool(self):
                def decorator(fn):
                    registered_tools[fn.__name__] = fn
                    return fn
                return decorator

        fake_mcp = types.ModuleType("mcp")
        fake_mcp_server = types.ModuleType("mcp.server")
        fake_mcp_server.FastMCP = FakeFastMCP  # type: ignore[attr-defined]

        saved = sys.modules.get("mcp")
        saved_srv = sys.modules.get("mcp.server")
        sys.modules["mcp"] = fake_mcp
        sys.modules["mcp.server"] = fake_mcp_server

        try:
            from auracode.mcp_server import create_mcp_server

            engine = _make_mock_engine(response_content="Here is the code")
            server = create_mcp_server(engine)
            assert server is not None
        finally:
            if saved is not None:
                sys.modules["mcp"] = saved
            else:
                sys.modules.pop("mcp", None)
            if saved_srv is not None:
                sys.modules["mcp.server"] = saved_srv
            else:
                sys.modules.pop("mcp.server", None)

        return registered_tools, engine

    async def test_auracode_generate_creates_correct_request(self, tools_and_engine) -> None:
        tools, engine = tools_and_engine
        result = await tools["auracode_generate"]("Write a function")
        assert result == "Here is the code"

        # Verify the engine received a correctly formed EngineRequest
        call_args = engine.execute.call_args[0][0]
        assert call_args.intent == RequestIntent.GENERATE_CODE
        assert call_args.prompt == "Write a function"
        assert call_args.adapter_name == "mcp"

    async def test_auracode_generate_with_custom_intent(self, tools_and_engine) -> None:
        tools, engine = tools_and_engine
        result = await tools["auracode_generate"]("Review my code", intent="review")

        call_args = engine.execute.call_args[0][0]
        assert call_args.intent == RequestIntent.REVIEW

    async def test_auracode_generate_invalid_intent_falls_back(self, tools_and_engine) -> None:
        tools, engine = tools_and_engine
        await tools["auracode_generate"]("test", intent="nonexistent_intent")

        call_args = engine.execute.call_args[0][0]
        assert call_args.intent == RequestIntent.GENERATE_CODE  # fallback

    async def test_auracode_generate_returns_error_string(self) -> None:
        """When engine returns an error, the tool returns 'Error: ...'."""
        registered_tools: dict[str, Any] = {}

        class FakeFastMCP:
            def __init__(self, name: str):
                pass
            def tool(self):
                def decorator(fn):
                    registered_tools[fn.__name__] = fn
                    return fn
                return decorator

        fake_mcp = types.ModuleType("mcp")
        fake_mcp_server = types.ModuleType("mcp.server")
        fake_mcp_server.FastMCP = FakeFastMCP  # type: ignore[attr-defined]

        saved = sys.modules.get("mcp")
        saved_srv = sys.modules.get("mcp.server")
        sys.modules["mcp"] = fake_mcp
        sys.modules["mcp.server"] = fake_mcp_server
        try:
            from auracode.mcp_server import create_mcp_server
            engine = _make_mock_engine(response_content="", response_error="model overloaded")
            create_mcp_server(engine)
        finally:
            if saved is not None:
                sys.modules["mcp"] = saved
            else:
                sys.modules.pop("mcp", None)
            if saved_srv is not None:
                sys.modules["mcp.server"] = saved_srv
            else:
                sys.modules.pop("mcp.server", None)

        result = await registered_tools["auracode_generate"]("test prompt")
        assert result.startswith("Error:")
        assert "model overloaded" in result

    async def test_auracode_explain_creates_explain_request(self, tools_and_engine, tmp_path) -> None:
        tools, engine = tools_and_engine
        # Create a real temp file so explain can read it
        test_file = tmp_path / "sample.py"
        test_file.write_text("x = 1\n", encoding="utf-8")

        result = await tools["auracode_explain"](str(test_file))
        assert result == "Here is the code"

        call_args = engine.execute.call_args[0][0]
        assert call_args.intent == RequestIntent.EXPLAIN_CODE
        assert "Explain" in call_args.prompt
        assert call_args.adapter_name == "mcp"
        # Context should include a file with the content we wrote
        assert call_args.context is not None
        assert len(call_args.context.files) == 1
        assert call_args.context.files[0].content == "x = 1\n"
        assert call_args.context.files[0].language == "py"

    async def test_auracode_review_creates_review_request(self, tools_and_engine, tmp_path) -> None:
        tools, engine = tools_and_engine
        test_file = tmp_path / "code.py"
        test_file.write_text("def f(): pass\n", encoding="utf-8")

        result = await tools["auracode_review"](str(test_file))
        assert result == "Here is the code"

        call_args = engine.execute.call_args[0][0]
        assert call_args.intent == RequestIntent.REVIEW
        assert "Review" in call_args.prompt
        assert call_args.context.files[0].content == "def f(): pass\n"

    async def test_auracode_models_returns_model_list(self, tools_and_engine) -> None:
        tools, engine = tools_and_engine
        engine.router.list_models.return_value = [
            ModelInfo(model_id="llama3", provider="ollama"),
            ModelInfo(model_id="claude", provider="anthropic"),
        ]
        result = await tools["auracode_models"]()
        assert "llama3" in result
        assert "ollama" in result
        assert "claude" in result
        assert "anthropic" in result

    async def test_auracode_models_empty(self, tools_and_engine) -> None:
        tools, engine = tools_and_engine
        engine.router.list_models.return_value = []
        result = await tools["auracode_models"]()
        assert result == "No models available"
