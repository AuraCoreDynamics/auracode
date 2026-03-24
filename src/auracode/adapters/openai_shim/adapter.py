"""OpenAIShimAdapter — translates OpenAI JSON to/from engine objects."""

from __future__ import annotations

import time
import uuid
from typing import Any

import click

from auracode.adapters.base import BaseAdapter
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent


class OpenAIShimAdapter(BaseAdapter):
    """Adapter bridging the OpenAI-compatible API layer to the engine."""

    @property
    def name(self) -> str:
        return "openai-shim"

    async def translate_request(self, raw_input: Any) -> EngineRequest:
        """Convert an OpenAI-format dict to an EngineRequest.

        Expected keys mirror the OpenAI ``/v1/chat/completions`` body:
            - ``messages`` (list[dict])  — required
            - ``model`` (str)            — optional
            - ``temperature`` (float)    — optional
            - ``max_tokens`` (int)       — optional
        """
        if not isinstance(raw_input, dict):
            raise TypeError(f"Expected dict, got {type(raw_input).__name__}")

        messages: list[dict[str, str]] = raw_input.get("messages", [])
        if not messages:
            raise ValueError("messages is required and must be non-empty")

        prompt = messages[-1].get("content", "")
        history = messages[:-1]

        # Simple intent heuristic.
        intent = RequestIntent.CHAT
        last_lower = prompt.lower()
        if any(kw in last_lower for kw in ("generate", "write", "create", "implement")):
            intent = RequestIntent.GENERATE_CODE

        options: dict[str, Any] = {}
        if "temperature" in raw_input:
            options["temperature"] = raw_input["temperature"]
        if "max_tokens" in raw_input:
            options["max_tokens"] = raw_input["max_tokens"]

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
            adapter_name=self.name,
            options=options,
        )

    async def translate_response(self, response: EngineResponse) -> Any:
        """Convert an EngineResponse to OpenAI ChatCompletion JSON."""
        usage = response.usage
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.model_used or "auracode",
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
                "total_tokens": ((usage.prompt_tokens + usage.completion_tokens) if usage else 0),
            },
        }

    def get_cli_group(self) -> click.Group | None:
        """No CLI commands for the shim adapter."""
        return None
