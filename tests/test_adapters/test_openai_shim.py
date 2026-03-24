"""Tests for OpenAIShimAdapter — request/response translation."""

from __future__ import annotations

import pytest

from auracode.adapters.openai_shim.adapter import OpenAIShimAdapter
from auracode.models.request import EngineResponse, RequestIntent, TokenUsage


@pytest.fixture()
def adapter() -> OpenAIShimAdapter:
    return OpenAIShimAdapter()


class TestOpenAIShimAdapterName:
    def test_name_returns_openai_shim(self, adapter: OpenAIShimAdapter) -> None:
        assert adapter.name == "openai-shim"


class TestTranslateRequest:
    async def test_basic_chat_message(self, adapter: OpenAIShimAdapter) -> None:
        """Single user message becomes a CHAT intent EngineRequest."""
        raw = {
            "messages": [{"role": "user", "content": "Hello world"}],
        }
        req = await adapter.translate_request(raw)
        assert req.prompt == "Hello world"
        assert req.intent == RequestIntent.CHAT
        assert req.adapter_name == "openai-shim"
        assert req.context is None  # no history -> no context

    async def test_generate_intent_from_keywords(self, adapter: OpenAIShimAdapter) -> None:
        """Keywords like 'generate', 'write', 'create' trigger GENERATE_CODE intent."""
        for keyword in ("generate", "write", "create", "implement"):
            raw = {
                "messages": [{"role": "user", "content": f"Please {keyword} a function"}],
            }
            req = await adapter.translate_request(raw)
            assert req.intent == RequestIntent.GENERATE_CODE, f"Failed for keyword: {keyword}"

    async def test_history_creates_session_context(self, adapter: OpenAIShimAdapter) -> None:
        """Multiple messages creates a SessionContext with history."""
        raw = {
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "How are you?"},
            ],
        }
        req = await adapter.translate_request(raw)
        assert req.prompt == "How are you?"
        assert req.context is not None
        assert len(req.context.history) == 2
        assert req.context.history[0]["role"] == "user"
        assert req.context.history[0]["content"] == "Hi"

    async def test_options_forwarded(self, adapter: OpenAIShimAdapter) -> None:
        """temperature and max_tokens appear in options dict."""
        raw = {
            "messages": [{"role": "user", "content": "test"}],
            "temperature": 0.7,
            "max_tokens": 512,
        }
        req = await adapter.translate_request(raw)
        assert req.options["temperature"] == 0.7
        assert req.options["max_tokens"] == 512

    async def test_empty_messages_raises(self, adapter: OpenAIShimAdapter) -> None:
        with pytest.raises(ValueError, match="messages is required"):
            await adapter.translate_request({"messages": []})

    async def test_non_dict_raises(self, adapter: OpenAIShimAdapter) -> None:
        with pytest.raises(TypeError, match="Expected dict"):
            await adapter.translate_request("not a dict")


class TestTranslateResponse:
    async def test_openai_format_structure(self, adapter: OpenAIShimAdapter) -> None:
        """Verify the response JSON has the OpenAI ChatCompletion structure."""
        resp = EngineResponse(
            request_id="r1",
            content="The answer is 42",
            model_used="test-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=25),
        )
        result = await adapter.translate_response(resp)

        assert result["object"] == "chat.completion"
        assert result["model"] == "test-model"
        assert result["id"].startswith("chatcmpl-")
        assert len(result["choices"]) == 1
        assert result["choices"][0]["message"]["role"] == "assistant"
        assert result["choices"][0]["message"]["content"] == "The answer is 42"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 25
        assert result["usage"]["total_tokens"] == 35

    async def test_response_without_usage(self, adapter: OpenAIShimAdapter) -> None:
        """When usage is None, token counts should be 0."""
        resp = EngineResponse(request_id="r2", content="hello", usage=None)
        result = await adapter.translate_response(resp)
        assert result["usage"]["prompt_tokens"] == 0
        assert result["usage"]["completion_tokens"] == 0
        assert result["usage"]["total_tokens"] == 0

    async def test_response_without_model(self, adapter: OpenAIShimAdapter) -> None:
        """When model_used is None, the output model defaults to 'auracode'."""
        resp = EngineResponse(request_id="r3", content="ok", model_used=None)
        result = await adapter.translate_response(resp)
        assert result["model"] == "auracode"


class TestGetCliGroup:
    def test_returns_none(self, adapter: OpenAIShimAdapter) -> None:
        assert adapter.get_cli_group() is None
