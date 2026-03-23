"""Tests for /v1/chat/completions and /v1/completions endpoints."""

from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — non-streaming
# ---------------------------------------------------------------------------


async def test_chat_completions_basic(client):
    """Valid request returns 200 with correct OpenAI schema."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert resp.status == 200
    body = await resp.json()

    # Top-level keys
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert isinstance(body["created"], int)
    assert body["model"] == "mock-model-v1"

    # Choices
    assert len(body["choices"]) == 1
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    assert "mock response to: Hello" in choice["message"]["content"]

    # Usage
    assert body["usage"]["prompt_tokens"] == 10
    assert body["usage"]["completion_tokens"] == 20
    assert body["usage"]["total_tokens"] == 30


async def test_chat_completions_missing_messages(client):
    """Request without messages returns 400."""
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "test-model"},
    )
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body


async def test_chat_completions_empty_messages(client):
    """Request with empty messages list returns 400."""
    resp = await client.post(
        "/v1/chat/completions",
        json={"model": "test-model", "messages": []},
    )
    assert resp.status == 400


async def test_chat_completions_with_history(client):
    """Multiple messages — history passed to engine."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Write a function"},
            ],
        },
    )
    assert resp.status == 200
    body = await resp.json()
    assert "mock response to: Write a function" in body["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — streaming
# ---------------------------------------------------------------------------


async def test_chat_completions_stream(client):
    """stream=true returns Server-Sent Events."""
    resp = await client.post(
        "/v1/chat/completions",
        json={
            "model": "test-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": True,
        },
    )
    assert resp.status == 200
    assert "text/event-stream" in resp.headers["Content-Type"]

    raw = await resp.read()
    text = raw.decode("utf-8")

    # Should contain data lines and [DONE]
    lines = [l for l in text.split("\n") if l.startswith("data: ")]
    assert len(lines) >= 2  # content chunk + stop chunk + [DONE]

    # First chunk should have content
    first_chunk = json.loads(lines[0].removeprefix("data: "))
    assert first_chunk["object"] == "chat.completion.chunk"
    assert "content" in first_chunk["choices"][0]["delta"]

    # Last data line is [DONE]
    assert lines[-1] == "data: [DONE]"


# ---------------------------------------------------------------------------
# POST /v1/completions (legacy)
# ---------------------------------------------------------------------------


async def test_completions_basic(client):
    """Legacy completions endpoint works."""
    resp = await client.post(
        "/v1/completions",
        json={"model": "test-model", "prompt": "def hello():"},
    )
    assert resp.status == 200
    body = await resp.json()

    assert body["object"] == "text_completion"
    assert body["id"].startswith("chatcmpl-")
    assert len(body["choices"]) == 1
    assert "mock response to: def hello():" in body["choices"][0]["text"]
    assert body["choices"][0]["finish_reason"] == "stop"


async def test_completions_missing_prompt(client):
    """Legacy endpoint without prompt returns 400."""
    resp = await client.post(
        "/v1/completions",
        json={"model": "test-model"},
    )
    assert resp.status == 400
    body = await resp.json()
    assert "error" in body
