"""End-to-end tests: request through engine to mock backend and back."""

from __future__ import annotations

import pytest

from auracode.engine.core import AuraCodeEngine
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent

from .conftest import IntegrationMockBackend


class TestFullPath:
    """Submit requests through the engine and verify the full round-trip."""

    @pytest.mark.asyncio
    async def test_execute_returns_well_formed_response(self, app_components):
        engine, _, _ = app_components
        req = EngineRequest(
            request_id="e2e-001",
            intent=RequestIntent.GENERATE_CODE,
            prompt="Write a fibonacci function",
            adapter_name="test",
        )
        resp = await engine.execute(req)
        assert isinstance(resp, EngineResponse)
        assert resp.request_id == "e2e-001"
        assert resp.content
        assert resp.error is None

    @pytest.mark.asyncio
    async def test_request_reaches_backend_with_correct_intent(self, app_components):
        engine, _, _ = app_components
        backend = engine.router
        assert isinstance(backend, IntegrationMockBackend)

        req = EngineRequest(
            request_id="e2e-002",
            intent=RequestIntent.REVIEW,
            prompt="Review this code",
            adapter_name="test",
        )
        await engine.execute(req)

        assert len(backend.calls) == 1
        call = backend.calls[0]
        assert call["intent"] == RequestIntent.REVIEW
        assert call["prompt"] == "Review this code"

    @pytest.mark.asyncio
    async def test_response_includes_model_and_usage(self, app_components):
        engine, _, _ = app_components
        req = EngineRequest(
            request_id="e2e-003",
            intent=RequestIntent.CHAT,
            prompt="Hello",
            adapter_name="test",
        )
        resp = await engine.execute(req)
        assert resp.model_used == "integration-mock-v1"
        assert resp.usage is not None
        assert resp.usage.prompt_tokens == 5
        assert resp.usage.completion_tokens == 15

    @pytest.mark.asyncio
    async def test_session_state_updated_after_execute(self, app_components):
        engine, _, _ = app_components
        req = EngineRequest(
            request_id="e2e-004",
            intent=RequestIntent.CHAT,
            prompt="First message",
            adapter_name="test",
        )
        await engine.execute(req)

        # Engine should have created a session and updated history
        # We can verify by checking the session manager
        # The session was created internally; verify at least one session exists
        assert engine.session_manager._sessions  # non-empty

        # Get the session and check history
        session_id = list(engine.session_manager._sessions.keys())[0]
        session = engine.get_session(session_id)
        assert session is not None
        assert len(session.history) == 2  # user + assistant
        assert session.history[0]["role"] == "user"
        assert session.history[0]["content"] == "First message"
        assert session.history[1]["role"] == "assistant"
        assert "integration mock response" in session.history[1]["content"]

    @pytest.mark.asyncio
    async def test_multiple_requests_accumulate_history(self, app_components):
        engine, _, _ = app_components

        for i in range(3):
            req = EngineRequest(
                request_id=f"e2e-multi-{i}",
                intent=RequestIntent.CHAT,
                prompt=f"Message {i}",
                adapter_name="test",
            )
            await engine.execute(req)

        # Each request creates a new session (no context provided)
        # so 3 sessions with 2 history entries each
        assert len(engine.session_manager._sessions) == 3

    @pytest.mark.asyncio
    async def test_adapter_translate_through_engine(self, app_components):
        """Test using the claude-code adapter's translate_request."""
        engine, adapters, _ = app_components
        adapter = adapters.get("claude-code")
        assert adapter is not None

        raw_input = {
            "prompt": "Write a test",
            "intent": "generate",
        }
        request = await adapter.translate_request(raw_input)
        assert request.intent == RequestIntent.GENERATE_CODE
        assert request.prompt == "Write a test"

        resp = await engine.execute(request)
        assert resp.error is None
        assert "integration mock response" in resp.content

    @pytest.mark.asyncio
    async def test_engine_handles_error_gracefully(self, integration_config):
        """Engine wraps backend errors in EngineResponse.error."""
        from tests.conftest import FailingRouterBackend

        engine = AuraCodeEngine(integration_config, FailingRouterBackend())
        req = EngineRequest(
            request_id="e2e-err-001",
            intent=RequestIntent.CHAT,
            prompt="This will fail",
            adapter_name="test",
        )
        resp = await engine.execute(req)
        assert resp.error is not None
        assert "backend unavailable" in resp.error


class TestMcpServerIntegration:
    """Verify create_mcp_server behavior end-to-end."""

    def test_mcp_missing_returns_none(self) -> None:
        """When mcp package is not installed, create_mcp_server returns None."""
        import sys
        from unittest.mock import MagicMock

        saved = sys.modules.get("mcp")
        saved_srv = sys.modules.get("mcp.server")
        sys.modules["mcp"] = None  # type: ignore[assignment]
        sys.modules["mcp.server"] = None  # type: ignore[assignment]
        try:
            from auracode.mcp_server import create_mcp_server

            result = create_mcp_server(engine=MagicMock())
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

    def test_mcp_available_returns_server_with_tools(self) -> None:
        """When mcp is available, server is returned with 4 tool registrations."""
        import sys
        import types
        from unittest.mock import MagicMock

        registered_tools: list[str] = []

        class FakeFastMCP:
            def __init__(self, name: str):
                self._name = name

            def tool(self):
                def decorator(fn):
                    registered_tools.append(fn.__name__)
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

            engine = MagicMock()
            result = create_mcp_server(engine)
            assert result is not None
            assert result._name == "auracode"
            # Verify core tools plus new FMoE tools were registered
            assert "auracode_generate" in registered_tools
            assert "auracode_explain" in registered_tools
            assert "auracode_review" in registered_tools
            assert "auracode_models" in registered_tools
            assert "auracode_plan" in registered_tools
            assert "auracode_refactor" in registered_tools
            assert "auracode_review_diff" in registered_tools
            assert "auracode_security_review" in registered_tools
            assert "auracode_trace" in registered_tools
            assert "auracode_write_file" in registered_tools
            assert "auracode_edit_file" in registered_tools
            assert "auracode_bash" in registered_tools
            assert len(registered_tools) == 12
        finally:
            if saved is not None:
                sys.modules["mcp"] = saved
            else:
                sys.modules.pop("mcp", None)
            if saved_srv is not None:
                sys.modules["mcp.server"] = saved_srv
            else:
                sys.modules.pop("mcp.server", None)
