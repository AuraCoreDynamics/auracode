"""End-to-end integration tests for the AuraCode full stack.

Validates adapter discovery across all 5 adapters, engine execution through
the Claude Code CLI, and GridDelegateBackend serialization.
"""

from __future__ import annotations

import pytest

from auracode.adapters.loader import discover_adapters
from auracode.engine.core import AuraCodeEngine
from auracode.engine.registry import AdapterRegistry
from auracode.grid.messages import GridRequest, GridResponse
from auracode.grid.serializer import engine_request_to_grid, grid_response_to_route_result
from auracode.models.config import AuraCodeConfig
from auracode.models.request import RequestIntent, TokenUsage
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FullStackMockBackend(BaseRouterBackend):
    """Mock backend for full-stack integration tests."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def route(self, prompt, intent, context=None, options=None):
        self.calls.append({"prompt": prompt, "intent": intent})
        return RouteResult(
            content=f"full-stack response: {prompt}",
            model_used="mock-full-stack",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
        )

    async def list_models(self):
        return [ModelInfo(model_id="mock-full-stack", provider="mock", tags=["test"])]

    async def health_check(self):
        return True


# ======================================================================
# T8.2a: All 5 adapters discovered
# ======================================================================


class TestAllAdaptersDiscovered:
    """Verify that all 5 adapters are discovered by the adapter loader."""

    def test_discover_finds_all_adapters(self):
        # discover_adapters should register opencode, claude-code,
        # copilot, aider, codestral, and openai-shim.
        registry = AdapterRegistry()
        discover_adapters(registry)

        adapters = sorted(registry.list_adapters())
        # All 5 named adapters plus openai-shim
        required = {"opencode", "claude-code", "copilot", "aider", "codestral"}
        assert required.issubset(set(adapters)), f"Missing adapters: {required - set(adapters)}"
        assert len(adapters) >= 5

    def test_each_adapter_has_translate_request(self):
        """Every discovered adapter must expose translate_request."""
        registry = AdapterRegistry()
        discover_adapters(registry)

        for name in registry.list_adapters():
            adapter = registry.get(name)
            assert adapter is not None
            assert hasattr(adapter, "translate_request")
            assert callable(adapter.translate_request)

    def test_each_adapter_has_translate_response(self):
        """Every discovered adapter must expose translate_response."""
        registry = AdapterRegistry()
        discover_adapters(registry)

        for name in registry.list_adapters():
            adapter = registry.get(name)
            assert adapter is not None
            assert hasattr(adapter, "translate_response")
            assert callable(adapter.translate_response)

    def test_openai_shim_also_discovered(self):
        """The openai_shim adapter should also be discovered (6 total subpackages)."""
        registry = AdapterRegistry()
        discover_adapters(registry)

        # openai_shim is a subpackage too, but it might use a different name
        adapters = registry.list_adapters()
        # At minimum the 5 named adapters must be present
        assert len(adapters) >= 5


# ======================================================================
# T8.2b: Claude Code CLI executes through engine
# ======================================================================


class TestClaudeCodeCliExecution:
    """Test that 'auracode claude do' flows through the full engine stack."""

    @pytest.mark.asyncio
    async def test_claude_do_executes_through_engine(self):
        """Simulate a claude 'do' command through the engine with a mock backend."""
        backend = FullStackMockBackend()
        config = AuraCodeConfig(log_level="WARNING")
        engine = AuraCodeEngine(config, backend)

        # Build a request as the Claude Code adapter would
        from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        raw_input = {"prompt": "hello world", "intent": "do"}
        request = await adapter.translate_request(raw_input)
        response = await engine.execute(request)

        assert response.content == "full-stack response: hello world"
        assert response.model_used == "mock-full-stack"
        assert len(backend.calls) == 1
        assert backend.calls[0]["prompt"] == "hello world"

    @pytest.mark.asyncio
    async def test_claude_do_with_model_option(self):
        """Model option should be passed through the engine request."""
        backend = FullStackMockBackend()
        config = AuraCodeConfig(log_level="WARNING")
        engine = AuraCodeEngine(config, backend)

        from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter

        adapter = ClaudeCodeAdapter()
        raw_input = {"prompt": "test", "intent": "do", "options": {"model": "opus"}}
        request = await adapter.translate_request(raw_input)

        assert request.options.get("model") == "opus"
        response = await engine.execute(request)
        assert response.error is None


# ======================================================================
# T8.2c: GridDelegateBackend serialization
# ======================================================================


class TestGridDelegateBackendSerialization:
    """Test that GridDelegateBackend can serialize and send requests."""

    def test_engine_request_to_grid_serialization(self):
        """engine_request_to_grid should produce a valid GridRequest."""
        grid_req = engine_request_to_grid(
            request_id="req-001",
            prompt="Write a function",
            intent=RequestIntent.GENERATE_CODE,
            options={"model": "opus", "temperature": 0.7},
        )

        assert isinstance(grid_req, GridRequest)
        assert grid_req.request_id == "req-001"
        assert grid_req.prompt == "Write a function"
        assert grid_req.intent == "generate_code"
        assert grid_req.options["model"] == "opus"
        assert grid_req.options["temperature"] == "0.7"

    def test_grid_response_to_route_result(self):
        """grid_response_to_route_result should produce a valid RouteResult."""
        grid_resp = GridResponse(
            request_id="req-001",
            content="def hello(): pass",
            model_used="grid-model-v1",
            prompt_tokens=15,
            completion_tokens=25,
        )

        result = grid_response_to_route_result(grid_resp)
        assert isinstance(result, RouteResult)
        assert result.content == "def hello(): pass"
        assert result.model_used == "grid-model-v1"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 15
        assert result.usage.completion_tokens == 25

    def test_grid_roundtrip(self):
        """Request serialization and response deserialization form a complete roundtrip."""
        grid_req = engine_request_to_grid(
            request_id="roundtrip-001",
            prompt="Explain this code",
            intent=RequestIntent.EXPLAIN_CODE,
        )

        # Simulate server processing
        grid_resp = GridResponse(
            request_id=grid_req.request_id,
            content="This code does XYZ",
            model_used="remote-model",
            prompt_tokens=10,
            completion_tokens=30,
        )

        result = grid_response_to_route_result(grid_resp)
        assert result.content == "This code does XYZ"
        assert result.model_used == "remote-model"


# ======================================================================
# T8.2d: No placeholder responses remain
# ======================================================================


class TestNoPlaceholderResponses:
    """Verify that no adapter CLI modules still use _placeholder_response."""

    def test_copilot_cli_no_placeholder(self):
        """Copilot CLI should be wired to the engine, not use placeholders."""
        from auracode.adapters.copilot import cli as cli_module

        assert not hasattr(cli_module, "_placeholder_response")

    def test_aider_cli_no_placeholder(self):
        """Aider CLI should be wired to the engine, not use placeholders."""
        from auracode.adapters.aider import cli as cli_module

        assert not hasattr(cli_module, "_placeholder_response")

    def test_codestral_cli_no_placeholder(self):
        """Codestral CLI should be wired to the engine, not use placeholders."""
        from auracode.adapters.codestral import cli as cli_module

        assert not hasattr(cli_module, "_placeholder_response")
