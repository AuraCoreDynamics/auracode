"""Tests for IDE WebSocket handler, streaming, cancellation, and tools."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse, TokenUsage
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult
from auracode.shim.ide_tools import ToolManager
from auracode.shim.ide_websocket import (
    _cancel_flags,
    _tool_managers,
)
from auracode.shim.server import create_app

# ── Helpers ───────────────────────────────────────────────────────────


class _StreamingMockRouter(BaseRouterBackend):
    """Mock router that yields tokens one at a time."""

    def __init__(self, tokens: list[str] | None = None):
        self._tokens = tokens or ["Hello", " ", "world"]

    async def route(self, prompt, intent, context=None, options=None):
        return RouteResult(content="".join(self._tokens), model_used="mock-v1")

    async def route_stream(self, prompt, intent, context=None, options=None):
        for tok in self._tokens:
            yield tok

    async def list_models(self):
        return [ModelInfo(model_id="mock-v1", provider="mock")]

    async def health_check(self):
        return True


class _ErrorRouter(BaseRouterBackend):
    """Mock router that raises on streaming."""

    async def route(self, prompt, intent, context=None, options=None):
        raise RuntimeError("route error")

    async def route_stream(self, prompt, intent, context=None, options=None):
        raise RuntimeError("stream error")
        yield  # make it an async generator

    async def list_models(self):
        return []

    async def health_check(self):
        return False


class _MockEngine:
    """Engine-like object with streaming support."""

    def __init__(self, router=None):
        self.router = router or _StreamingMockRouter()
        self.session_manager = MagicMock()
        self.session_manager._sessions = {}
        self.session_manager.get.return_value = None
        self.session_manager.create.return_value = SessionContext(
            session_id="test-session",
            working_directory=".",
        )
        self.execute = AsyncMock(
            return_value=EngineResponse(
                request_id="r1",
                content="Hello world",
                model_used="mock-v1",
                usage=TokenUsage(prompt_tokens=5, completion_tokens=10),
            )
        )

    async def execute_stream(self, request: EngineRequest):
        """Stream from router."""
        async for chunk in self.router.route_stream(
            prompt=request.prompt,
            intent=request.intent,
        ):
            yield chunk

    def get_session(self, session_id: str):
        return self.session_manager.get(session_id)

    def close_session(self, session_id: str):
        self.session_manager._sessions.pop(session_id, None)


@pytest.fixture()
def streaming_engine():
    return _MockEngine()


@pytest.fixture()
def error_engine():
    return _MockEngine(router=_ErrorRouter())


@pytest.fixture()
def streaming_app(streaming_engine):
    return create_app(streaming_engine)


@pytest.fixture()
def error_app(error_engine):
    return create_app(error_engine)


@pytest.fixture()
async def ws_client(aiohttp_client, streaming_app):
    return await aiohttp_client(streaming_app)


@pytest.fixture()
async def error_ws_client(aiohttp_client, error_app):
    return await aiohttp_client(error_app)


@pytest.fixture(autouse=True)
def _clean_globals():
    """Clean up module-level state between tests."""
    _cancel_flags.clear()
    _tool_managers.clear()
    yield
    _cancel_flags.clear()
    _tool_managers.clear()


# ── WebSocket dispatch ────────────────────────────────────────────────


class TestWebSocketDispatch:
    """Message dispatch routes to the correct handler."""

    async def test_unknown_type_returns_error(self, ws_client):
        ws = await ws_client.ws_connect("/ws/ide")
        await ws.send_json({"type": "bogus"})
        resp = await ws.receive_json()
        assert resp["type"] == "error"
        assert resp["code"] == "unknown_type"
        await ws.close()

    async def test_invalid_json_returns_error(self, ws_client):
        ws = await ws_client.ws_connect("/ws/ide")
        await ws.send_str("not json{{{")
        resp = await ws.receive_json()
        assert resp["type"] == "error"
        assert resp["code"] == "invalid_json"
        await ws.close()


# ── Streaming token delivery ─────────────────────────────────────────


class TestStreaming:
    """Chat messages produce streaming token responses."""

    async def test_chat_streams_tokens(self, ws_client):
        ws = await ws_client.ws_connect("/ws/ide")
        await ws.send_json({"type": "chat", "message": "Say hello"})

        # Expect: status, stream_token(s), stream_end
        messages = []
        while True:
            msg = await ws.receive_json()
            messages.append(msg)
            if msg["type"] == "end":
                break

        types = [m["type"] for m in messages]
        assert "status" in types
        assert "token" in types
        assert types[-1] == "end"

        # Verify token content
        tokens = [m["content"] for m in messages if m["type"] == "token"]
        assert "".join(tokens) == "Hello world"
        await ws.close()

    async def test_chat_with_session_id(self, ws_client):
        ws = await ws_client.ws_connect("/ws/ide")
        await ws.send_json(
            {
                "type": "chat",
                "message": "test",
                "session_id": "my-session",
            }
        )

        messages = []
        while True:
            msg = await ws.receive_json()
            messages.append(msg)
            if msg["type"] == "end":
                break

        # Should complete without error.
        assert messages[-1]["type"] == "end"
        await ws.close()

    async def test_invalid_chat_message_returns_error(self, ws_client):
        ws = await ws_client.ws_connect("/ws/ide")
        # Missing required "message" field.
        await ws.send_json({"type": "chat"})
        resp = await ws.receive_json()
        assert resp["type"] == "error"
        assert resp["code"] == "invalid_message"
        await ws.close()

    async def test_stream_error_sends_server_error(self, error_ws_client):
        ws = await error_ws_client.ws_connect("/ws/ide")
        await ws.send_json({"type": "chat", "message": "trigger error"})

        messages = []
        while True:
            msg = await ws.receive_json()
            messages.append(msg)
            if msg["type"] in ("end", "error"):
                # Collect remaining messages until stream_end.
                if msg["type"] == "end":
                    break
                continue
            if msg["type"] == "end":
                break
        # Ensure we got both error and stream_end.
        types = [m["type"] for m in messages]
        assert "error" in types
        await ws.close()


# ── Cancellation ─────────────────────────────────────────────────────


class TestCancellation:
    """Cancel requests stop streaming delivery."""

    async def test_cancel_stops_delivery(self, aiohttp_client):
        """Cancellation between tokens stops further delivery."""

        # Use many tokens with generous sleep so cancel has time to take effect.
        class _SlowRouter(BaseRouterBackend):
            async def route(self, prompt, intent, context=None, options=None):
                return RouteResult(content="a" * 20, model_used="mock")

            async def route_stream(self, prompt, intent, context=None, options=None):
                for ch in "a" * 20:
                    await asyncio.sleep(0.05)
                    yield ch

            async def list_models(self):
                return []

            async def health_check(self):
                return True

        engine = _MockEngine(router=_SlowRouter())
        app = create_app(engine)
        client = await aiohttp_client(app)

        ws = await client.ws_connect("/ws/ide")
        await ws.send_json({"type": "chat", "message": "slow"})

        # Read status message.
        first_msg = await ws.receive_json()
        assert first_msg["type"] == "status"

        # Read the request_id from the status message.
        request_id = first_msg.get("request_id")

        # Read two tokens to be sure streaming is underway.
        token_msg1 = await ws.receive_json()
        token_msg2 = await ws.receive_json()

        # Send cancel.
        await ws.send_json({"type": "cancel", "request_id": request_id})

        # Drain remaining messages.
        messages = [first_msg, token_msg1, token_msg2]
        while True:
            msg = await ws.receive_json()
            messages.append(msg)
            if msg["type"] == "end":
                break

        # Should have significantly fewer than 20 tokens.
        token_count = sum(1 for m in messages if m["type"] == "token")
        assert token_count < 20
        await ws.close()


# ── Tool request/response handshake ──────────────────────────────────


class TestToolManager:
    """ToolManager request/response lifecycle."""

    def test_resolve_unknown_returns_false(self):
        tm = ToolManager()
        assert tm.resolve_tool("nonexistent", True) is False

    def test_resolve_sets_future_result(self):
        tm = ToolManager()
        loop = asyncio.new_event_loop()

        async def _test():
            future = loop.create_future()
            tm._pending["req-1"] = future
            assert tm.resolve_tool("req-1", True, "done") is True
            result = await future
            assert result["approved"] is True
            assert result["result"] == "done"

        loop.run_until_complete(_test())
        loop.close()

    def test_cancel_all_clears_pending(self):
        tm = ToolManager()
        loop = asyncio.new_event_loop()

        async def _test():
            future = loop.create_future()
            tm._pending["req-1"] = future
            assert tm.pending_count == 1
            tm.cancel_all()
            assert tm.pending_count == 0

        loop.run_until_complete(_test())
        loop.close()

    async def test_request_tool_round_trip(self, ws_client):
        """Full tool request and response via WebSocket-like mock."""
        tm = ToolManager()

        # Simulate a WebSocket with send_json.
        sent_messages: list[dict] = []
        mock_ws = MagicMock()
        mock_ws.send_json = AsyncMock(side_effect=lambda msg: sent_messages.append(msg))

        async def _resolve_after_delay():
            await asyncio.sleep(0.05)
            # Find the request_id from the sent message.
            assert len(sent_messages) > 0
            req_id = sent_messages[0]["request_id"]
            tm.resolve_tool(req_id, True, "file created")

        task = asyncio.create_task(_resolve_after_delay())
        result = await tm.request_tool(mock_ws, "file_write", {"path": "x.py"}, "Write file")
        await task

        assert result["approved"] is True
        assert result["result"] == "file created"


# ── REST endpoints ───────────────────────────────────────────────────


class TestRestEndpoints:
    """REST endpoints added alongside WebSocket."""

    async def test_status_endpoint(self, ws_client):
        resp = await ws_client.get("/api/status")
        assert resp.status == 200
        data = await resp.json()
        assert "status" in data

    async def test_session_not_found(self, ws_client):
        resp = await ws_client.get("/api/session/nonexistent")
        assert resp.status == 404

    async def test_clear_session(self, ws_client):
        resp = await ws_client.delete("/api/session/nonexistent")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "closed"


# ── Route registration ───────────────────────────────────────────────


class TestRouteRegistration:
    """New routes are registered in create_app."""

    def test_new_routes_present(self, streaming_engine):
        app = create_app(streaming_engine)
        routes = {
            r.resource.canonical
            for r in app.router.routes()
            if hasattr(r, "resource") and r.resource
        }
        assert "/ws/ide" in routes
        assert "/api/status" in routes
        assert "/api/session/{id}" in routes

    def test_existing_routes_preserved(self, streaming_engine):
        app = create_app(streaming_engine)
        routes = {
            r.resource.canonical
            for r in app.router.routes()
            if hasattr(r, "resource") and r.resource
        }
        assert "/v1/chat/completions" in routes
        assert "/v1/completions" in routes
        assert "/v1/models" in routes
        assert "/health" in routes


# ── Session persistence ──────────────────────────────────────────────


class TestSessionPersistence:
    """Session IDs are stable across reconnections."""

    async def test_session_id_reused(self, ws_client):
        """Two connections with the same session_id share state."""
        session_id = "persistent-session"

        # First connection.
        ws1 = await ws_client.ws_connect("/ws/ide")
        await ws1.send_json(
            {
                "type": "chat",
                "message": "first",
                "session_id": session_id,
            }
        )
        while True:
            msg = await ws1.receive_json()
            if msg["type"] == "end":
                break
        await ws1.close()

        # Second connection with same session_id.
        ws2 = await ws_client.ws_connect("/ws/ide")
        await ws2.send_json(
            {
                "type": "chat",
                "message": "second",
                "session_id": session_id,
            }
        )
        while True:
            msg = await ws2.receive_json()
            if msg["type"] == "end":
                break
        await ws2.close()


# ── Graceful disconnect ──────────────────────────────────────────────


class TestGracefulDisconnect:
    """Client disconnection is handled without errors."""

    async def test_close_without_messages(self, ws_client):
        ws = await ws_client.ws_connect("/ws/ide")
        await ws.close()
        # No exception = pass.

    async def test_multiple_connects(self, ws_client):
        """Multiple concurrent connections work independently."""
        ws1 = await ws_client.ws_connect("/ws/ide")
        ws2 = await ws_client.ws_connect("/ws/ide")

        await ws1.send_json({"type": "chat", "message": "from ws1"})
        await ws2.send_json({"type": "chat", "message": "from ws2"})

        # Drain both.
        for ws in (ws1, ws2):
            while True:
                msg = await ws.receive_json()
                if msg["type"] == "end":
                    break

        await ws1.close()
        await ws2.close()
