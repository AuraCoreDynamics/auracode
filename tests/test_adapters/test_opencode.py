"""Tests for the OpenCode adapter and formatter."""

from __future__ import annotations

import pytest

from auracode.adapters.loader import discover_adapters
from auracode.adapters.opencode.adapter import OpenCodeAdapter
from auracode.adapters.opencode.formatter import format_response
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    RequestIntent,
    TokenUsage,
)


@pytest.fixture()
def adapter() -> OpenCodeAdapter:
    return OpenCodeAdapter()


@pytest.fixture()
def sample_response() -> EngineResponse:
    return EngineResponse(
        request_id="oc-001",
        content="Here is your code:",
        model_used="local-codellama",
        usage=TokenUsage(prompt_tokens=30, completion_tokens=80),
        artifacts=[
            FileArtifact(
                path="src/example.py",
                content="def greet():\n    print('Hello')\n",
                action="create",
            ),
        ],
    )


class TestOpenCodeAdapter:
    """OpenCodeAdapter unit tests."""

    def test_name(self, adapter: OpenCodeAdapter) -> None:
        assert adapter.name == "opencode"

    @pytest.mark.asyncio
    async def test_translate_request_chat(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Hello", "intent": "chat"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.CHAT
        assert req.prompt == "Hello"
        assert req.adapter_name == "opencode"
        assert req.request_id  # non-empty UUID string

    @pytest.mark.asyncio
    async def test_translate_request_generate(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Write tests", "intent": "generate"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE

    @pytest.mark.asyncio
    async def test_translate_request_do(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Write tests", "intent": "do"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE

    @pytest.mark.asyncio
    async def test_translate_request_explain(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Explain this", "intent": "explain"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.EXPLAIN_CODE

    @pytest.mark.asyncio
    async def test_translate_request_review(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Review this", "intent": "review"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.REVIEW

    @pytest.mark.asyncio
    async def test_translate_request_plan(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Plan this out", "intent": "plan"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.PLAN

    @pytest.mark.asyncio
    async def test_translate_request_write(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Write a parser", "intent": "write"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE

    @pytest.mark.asyncio
    async def test_translate_request_default_intent(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Something unknown", "intent": "unknown_thing"}
        req = await adapter.translate_request(raw)
        assert req.intent == RequestIntent.CHAT  # falls back to chat

    @pytest.mark.asyncio
    async def test_translate_request_with_options(self, adapter: OpenCodeAdapter) -> None:
        raw = {"prompt": "Hello", "options": {"model": "opus"}}
        req = await adapter.translate_request(raw)
        assert req.options == {"model": "opus"}

    @pytest.mark.asyncio
    async def test_translate_request_with_context_files(
        self,
        adapter: OpenCodeAdapter,
        tmp_path,
    ) -> None:
        test_file = tmp_path / "example.py"
        test_file.write_text("print('hi')", encoding="utf-8")
        raw = {"prompt": "Explain this", "intent": "explain", "context_files": [str(test_file)]}
        req = await adapter.translate_request(raw)
        assert req.context is not None
        assert len(req.context.files) == 1
        assert req.context.files[0].content == "print('hi')"
        assert req.context.files[0].language == "py"

    @pytest.mark.asyncio
    async def test_translate_request_type_error(self, adapter: OpenCodeAdapter) -> None:
        with pytest.raises(TypeError):
            await adapter.translate_request("not a dict")

    @pytest.mark.asyncio
    async def test_translate_response(
        self,
        adapter: OpenCodeAdapter,
        sample_response: EngineResponse,
    ) -> None:
        result = await adapter.translate_response(sample_response)
        assert isinstance(result, str)
        assert "Here is your code:" in result

    def test_get_cli_group_returns_none(self, adapter: OpenCodeAdapter) -> None:
        assert adapter.get_cli_group() is None


class TestOpenCodeFormatter:
    """Formatter unit tests."""

    def test_format_with_model(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response, show_model=True, show_usage=False)
        assert "Here is your code:" in output
        assert "local-codellama" in output
        assert "example.py" in output

    def test_format_without_model(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response, show_model=False, show_usage=False)
        assert "Here is your code:" in output
        assert "local-codellama" not in output

    def test_format_with_usage(self, sample_response: EngineResponse) -> None:
        output = format_response(sample_response, show_model=False, show_usage=True)
        assert "30+80=110 tokens" in output

    def test_format_error(self) -> None:
        resp = EngineResponse(
            request_id="err-001",
            content="",
            error="something went wrong",
        )
        output = format_response(resp, show_model=True, show_usage=False)
        assert "Error" in output
        assert "something went wrong" in output

    def test_format_delete_artifact(self) -> None:
        resp = EngineResponse(
            request_id="del-001",
            content="Removed file",
            artifacts=[FileArtifact(path="old.py", content="", action="delete")],
        )
        output = format_response(resp, show_model=True, show_usage=False)
        assert "Deleted" in output
        assert "file removed" in output


class TestOpenCodeDiscovery:
    """Verify the opencode adapter is discovered by the loader."""

    def test_discover_finds_opencode(self) -> None:
        registry = AdapterRegistry()
        discover_adapters(registry)
        assert "opencode" in registry.list_adapters()
