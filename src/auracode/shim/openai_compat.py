"""OpenAI-compatible chat/completions handlers."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from aiohttp import web

from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent


def _generate_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _detect_intent(messages: list[dict[str, str]]) -> RequestIntent:
    """Heuristic intent detection from the message list."""
    if not messages:
        return RequestIntent.CHAT
    last = messages[-1].get("content", "").lower()
    if any(kw in last for kw in ("generate", "write", "create", "implement")):
        return RequestIntent.GENERATE_CODE
    return RequestIntent.CHAT


def _build_engine_request(
    prompt: str,
    history: list[dict[str, str]],
    intent: RequestIntent,
    options: dict[str, Any],
) -> EngineRequest:
    """Create an EngineRequest from OpenAI-format parameters."""
    context: SessionContext | None = None
    if history:
        context = SessionContext(
            session_id=str(uuid.uuid4()),
            working_directory=".",
            history=history,
        )
    return EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=intent,
        prompt=prompt,
        context=context,
        adapter_name="openai-shim",
        options=options,
    )


def _format_chat_response(
    response: EngineResponse, model: str, completion_id: str
) -> dict[str, Any]:
    """Build an OpenAI ChatCompletion JSON dict."""
    usage = response.usage
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response.content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": (
                (usage.prompt_tokens + usage.completion_tokens) if usage else 0
            ),
        },
    }


def _format_completion_response(
    response: EngineResponse, model: str, completion_id: str
) -> dict[str, Any]:
    """Build an OpenAI (legacy) Completion JSON dict."""
    usage = response.usage
    return {
        "id": completion_id,
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "text": response.content,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": (
                (usage.prompt_tokens + usage.completion_tokens) if usage else 0
            ),
        },
    }


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------


async def chat_completions(request: web.Request) -> web.StreamResponse:
    """Handle POST /v1/chat/completions (OpenAI-compatible)."""
    body = await request.json()

    messages: list[dict[str, str]] | None = body.get("messages")
    if not messages:
        return web.json_response(
            {
                "error": {
                    "message": "messages is required and must be non-empty.",
                    "type": "invalid_request_error",
                    "code": "missing_messages",
                }
            },
            status=400,
        )

    model: str = body.get("model", "auracode")
    stream: bool = body.get("stream", False)
    temperature: float | None = body.get("temperature")
    max_tokens: int | None = body.get("max_tokens")

    # Extract prompt (last user message) and history (everything before).
    prompt = messages[-1].get("content", "")
    history = messages[:-1]
    intent = _detect_intent(messages)

    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if max_tokens is not None:
        options["max_tokens"] = max_tokens

    engine_request = _build_engine_request(prompt, history, intent, options)
    engine = request.app["engine"]
    response: EngineResponse = await engine.execute(engine_request)

    completion_id = _generate_id()
    used_model = response.model_used or model

    if stream:
        return await _stream_response(request, response, used_model, completion_id)

    return web.json_response(
        _format_chat_response(response, used_model, completion_id)
    )


async def _stream_response(
    request: web.Request,
    response: EngineResponse,
    model: str,
    completion_id: str,
) -> web.StreamResponse:
    """Stream the response as Server-Sent Events."""
    stream_response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await stream_response.prepare(request)

    # Send the content as a single chunk (engine doesn't stream natively).
    chunk_data = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": response.content},
                "finish_reason": None,
            }
        ],
    }
    await stream_response.write(
        f"data: {json.dumps(chunk_data)}\n\n".encode("utf-8")
    )

    # Send the final stop chunk.
    stop_data = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    await stream_response.write(
        f"data: {json.dumps(stop_data)}\n\n".encode("utf-8")
    )
    await stream_response.write(b"data: [DONE]\n\n")
    await stream_response.write_eof()
    return stream_response


# ---------------------------------------------------------------------------
# POST /v1/completions (legacy)
# ---------------------------------------------------------------------------


async def completions(request: web.Request) -> web.StreamResponse:
    """Handle POST /v1/completions (legacy OpenAI Completion endpoint)."""
    body = await request.json()

    prompt: str | None = body.get("prompt")
    if not prompt:
        return web.json_response(
            {
                "error": {
                    "message": "prompt is required.",
                    "type": "invalid_request_error",
                    "code": "missing_prompt",
                }
            },
            status=400,
        )

    model: str = body.get("model", "auracode")
    temperature: float | None = body.get("temperature")
    max_tokens: int | None = body.get("max_tokens")

    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if max_tokens is not None:
        options["max_tokens"] = max_tokens

    engine_request = _build_engine_request(
        prompt, [], RequestIntent.COMPLETE_CODE, options
    )
    engine = request.app["engine"]
    response: EngineResponse = await engine.execute(engine_request)

    completion_id = _generate_id()
    used_model = response.model_used or model

    return web.json_response(
        _format_completion_response(response, used_model, completion_id)
    )
