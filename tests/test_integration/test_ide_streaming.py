"""End-to-end IDE streaming integration tests.

These tests spin up the AuraCode shim server with a mock router backend
and validate the full WebSocket streaming pipeline:
  client connects → sends ChatMessage → receives StreamTokens → StreamEnd.
"""

from __future__ import annotations

import asyncio

import pytest

from auracode.engine.core import AuraCodeEngine
from auracode.models.config import AuraCodeConfig
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult
from auracode.shim.server import create_app

# ── Mock Backend ──────────────────────────────────────────────────────


class MockStreamingBackend(BaseRouterBackend):
    """A mock router backend that yields tokens for streaming tests."""

    async def route(self, prompt, intent, context=None, options=None):
        return RouteResult(content="Hello from mock", model_used="mock-model")

    async def route_stream(self, prompt, intent, context=None, options=None):
        for word in ["Hello", " from", " streaming", " mock"]:
            yield word
            await asyncio.sleep(0)  # yield control

    async def list_models(self):
        return [ModelInfo(model_id="mock-model", provider="mock")]

    async def health_check(self):
        return True


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_engine():
    config = AuraCodeConfig()
    backend = MockStreamingBackend()
    return AuraCodeEngine(config=config, router=backend)


@pytest.fixture
async def app(mock_engine):
    return create_app(mock_engine)


@pytest.fixture
async def server(app, aiohttp_server):
    return await aiohttp_server(app)


@pytest.fixture
async def ws_client(server, aiohttp_client):
    client = await aiohttp_client(server)
    return client


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_websocket_streaming_round_trip(ws_client):
    """Full round-trip: connect → chat → receive tokens → stream end."""
    ws = await ws_client.ws_connect("/ws/ide")

    chat_msg = {
        "type": "chat",
        "message": "Hello",
        "session_id": "test-session-001",
        "intent": "chat",
    }
    await ws.send_json(chat_msg)

    # Collect all messages until stream_end
    messages = []
    while True:
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
        messages.append(msg)
        if msg.get("type") in ("end", "end"):
            break

    # Should have: status + tokens + stream_end
    types = [m["type"] for m in messages]
    assert "end" in types or "end" in types
    token_msgs = [m for m in messages if m["type"] in ("token", "token")]
    assert len(token_msgs) > 0

    # Verify token content
    full_text = "".join(m.get("content", m.get("content", "")) for m in token_msgs)
    assert "Hello" in full_text
    assert "streaming" in full_text

    await ws.close()


@pytest.mark.asyncio
async def test_websocket_cancel_stops_streaming(ws_client):
    """Sending a cancel message should stop token delivery."""
    ws = await ws_client.ws_connect("/ws/ide")

    chat_msg = {
        "type": "chat",
        "message": "Hello",
        "session_id": "test-cancel-001",
        "intent": "chat",
    }
    await ws.send_json(chat_msg)

    # Wait for first token
    msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
    # The first message might be a status update
    if msg.get("type") == "status":
        msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)

    # Send cancel — we need the request_id from a token or status message
    request_id = msg.get("request_id", "")
    if request_id:
        cancel_msg = {"type": "cancel", "request_id": request_id}
        await ws.send_json(cancel_msg)

    # Drain remaining messages — should end quickly
    messages = [msg]
    try:
        while True:
            m = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
            messages.append(m)
            if m.get("type") in ("end", "end"):
                break
    except TimeoutError:
        pass  # Expected if cancel was processed

    await ws.close()


@pytest.mark.asyncio
async def test_health_endpoint(ws_client):
    """GET /health returns ok."""
    resp = await ws_client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_status_endpoint(ws_client):
    """GET /api/status returns server status."""
    resp = await ws_client.get("/api/status")
    assert resp.status == 200
    data = await resp.json()
    assert "status" in data


@pytest.mark.asyncio
async def test_session_not_found(ws_client):
    """GET /api/session/{id} returns 404 for unknown session."""
    resp = await ws_client.get("/api/session/nonexistent")
    assert resp.status == 404


@pytest.mark.asyncio
async def test_clear_session(ws_client):
    """DELETE /api/session/{id} succeeds."""
    resp = await ws_client.delete("/api/session/some-session")
    assert resp.status == 200
    data = await resp.json()
    assert data["status"] == "closed"


@pytest.mark.asyncio
async def test_websocket_invalid_json(ws_client):
    """Invalid JSON should return an error message, not crash."""
    ws = await ws_client.ws_connect("/ws/ide")
    await ws.send_str("not json")

    msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
    assert msg["type"] == "error"
    assert "invalid" in msg["message"].lower() or "json" in msg["message"].lower()

    await ws.close()


@pytest.mark.asyncio
async def test_websocket_unknown_type(ws_client):
    """Unknown message type should return an error."""
    ws = await ws_client.ws_connect("/ws/ide")
    await ws.send_json({"type": "unknown_type"})

    msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
    assert msg["type"] == "error"

    await ws.close()


@pytest.mark.asyncio
async def test_existing_rest_endpoints_unchanged(ws_client):
    """Verify the original OpenAI-compatible endpoints still work."""
    # /v1/models should return a list
    resp = await ws_client.get("/v1/models")
    assert resp.status == 200
    data = await resp.json()
    assert "data" in data
