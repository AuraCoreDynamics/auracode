"""Tests for AuraCode TG6: Routing Context Adoption.

Covers:
- RouteResult carries routing_context when AuraRouter provides it
- ExecutionMetadata includes routing_context via engine
- OpenAI-compatible shim surfaces routing context
- Hard-route degradation produces DegradationNotice
- Grid serialization preserves routing context
- Backwards compatibility (None when not present)
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest

from auracode.models.request import (
    DegradationNotice,
    EngineResponse,
    ExecutionMetadata,
    RequestIntent,
    TokenUsage,
)
from auracode.routing.base import RouteResult

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_routing_context(
    strategy: str = "pipeline",
    confidence: float = 0.92,
    complexity: int = 2,
    hard_routed: bool = False,
    simulated_cost: float = 0.0,
) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "confidence_score": confidence,
        "complexity_score": complexity,
        "selected_route": "coding",
        "analyzer_chain": ["edge_complexity", "slm_intent"],
        "intent": "SIMPLE_CODE",
        "hard_routed": hard_routed,
        "simulated_cost_avoided": simulated_cost,
    }


class _FakeRoutingContext:
    """Simulates aurarouter.analyzer_protocol.RoutingContext."""

    def __init__(self, **kwargs: Any) -> None:
        self.strategy = kwargs.get("strategy", "pipeline")
        self.confidence_score = kwargs.get("confidence_score", 0.92)
        self.complexity_score = kwargs.get("complexity_score", 2)
        self.selected_route = kwargs.get("selected_route", "coding")
        self.analyzer_chain = kwargs.get("analyzer_chain", ["edge_complexity"])
        self.intent = kwargs.get("intent", "SIMPLE_CODE")
        self.hard_routed = kwargs.get("hard_routed", False)
        self.simulated_cost_avoided = kwargs.get("simulated_cost_avoided", 0.0)


class _FakeGenerateResult:
    """Simulates aurarouter.savings.models.GenerateResult."""

    def __init__(
        self,
        text: str = "generated output",
        model_id: str = "ollama:llama3:8b",
        routing_context: _FakeRoutingContext | None = None,
    ) -> None:
        self.text = text
        self.model_id = model_id
        self.routing_context = routing_context


def _import_embedded():
    """(Re-)import EmbeddedRouterBackend after patching sys.modules."""
    import auracode.routing.embedded as mod

    importlib.reload(mod)
    return mod.EmbeddedRouterBackend


@pytest.fixture()
def _patch_aurarouter_with_rc(request):
    """Inject aurarouter mocks with a configurable GenerateResult."""
    routing_context = getattr(request, "param", None)  # optional indirect param
    fake_result = _FakeGenerateResult(routing_context=routing_context)

    ar = ModuleType("aurarouter")
    ar_config = ModuleType("aurarouter.config")
    ar_fabric = ModuleType("aurarouter.fabric")

    config_loader = MagicMock()
    config_loader.get_role_chain = MagicMock(return_value=["ollama:llama3:8b"])
    config_loader.get_all_model_ids = MagicMock(return_value=["ollama:llama3:8b"])
    config_loader.get_all_roles = MagicMock(return_value=["coder"])

    fabric = MagicMock()
    fabric.execute = MagicMock(return_value=fake_result)

    config_cls = MagicMock(return_value=config_loader)
    fabric_cls = MagicMock(return_value=fabric)

    ar_config.ConfigLoader = config_cls  # type: ignore[attr-defined]
    ar_fabric.ComputeFabric = fabric_cls  # type: ignore[attr-defined]

    originals: dict[str, ModuleType | None] = {}
    for key in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]:
        originals[key] = sys.modules.get(key)

    sys.modules["aurarouter"] = ar
    sys.modules["aurarouter.config"] = ar_config
    sys.modules["aurarouter.fabric"] = ar_fabric

    yield {"fabric": fabric, "fake_result": fake_result, "config_loader": config_loader}

    for key, orig in originals.items():
        if orig is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = orig


# ---------------------------------------------------------------------------
# T6.1: RouteResult carries routing_context field
# ---------------------------------------------------------------------------


class TestRouteResultModel:
    def test_routing_context_field_exists(self):
        result = RouteResult(content="hello", model_used="test-model")
        assert hasattr(result, "routing_context")
        assert result.routing_context is None

    def test_routing_context_can_be_set(self):
        ctx = _make_routing_context()
        result = RouteResult(content="hello", model_used="test-model", routing_context=ctx)
        assert result.routing_context == ctx
        assert result.routing_context["strategy"] == "pipeline"

    def test_routing_context_serializable(self):
        ctx = _make_routing_context(hard_routed=True, simulated_cost=0.0042)
        result = RouteResult(content="hello", model_used="test-model", routing_context=ctx)
        dumped = result.model_dump()
        assert dumped["routing_context"]["hard_routed"] is True
        assert abs(dumped["routing_context"]["simulated_cost_avoided"] - 0.0042) < 1e-6


# ---------------------------------------------------------------------------
# T6.2: EmbeddedRouterBackend extracts routing_context from GenerateResult
# ---------------------------------------------------------------------------


class TestEmbeddedRoutingContextExtraction:
    @pytest.mark.asyncio
    async def test_routing_context_none_when_not_present(self, _patch_aurarouter_with_rc):
        """Backwards compat: no routing context on GenerateResult.

        RouteResult.routing_context must be None when routing_context is absent.
        """
        cls = _import_embedded()
        backend = cls()
        result = await backend.route(
            prompt="Write a function",
            intent=RequestIntent.GENERATE_CODE,
        )
        assert result.routing_context is None

    @pytest.mark.asyncio
    async def test_routing_context_extracted_from_generate_result(self):
        """When GenerateResult has routing_context, it should be in RouteResult."""
        rc = _FakeRoutingContext(
            strategy="pipeline",
            confidence_score=0.94,
            complexity_score=2,
            hard_routed=False,
            simulated_cost_avoided=0.0,
        )
        fake_result = _FakeGenerateResult(routing_context=rc)

        ar = ModuleType("aurarouter")
        ar_config = ModuleType("aurarouter.config")
        ar_fabric = ModuleType("aurarouter.fabric")

        config_loader = MagicMock()
        config_loader.get_role_chain = MagicMock(return_value=["ollama:llama3:8b"])
        config_loader.get_all_model_ids = MagicMock(return_value=["ollama:llama3:8b"])
        fabric = MagicMock()
        fabric.execute = MagicMock(return_value=fake_result)

        ar_config.ConfigLoader = MagicMock(return_value=config_loader)  # type: ignore
        ar_fabric.ComputeFabric = MagicMock(return_value=fabric)  # type: ignore

        orig = {
            k: sys.modules.get(k) for k in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        }
        sys.modules.update(
            {"aurarouter": ar, "aurarouter.config": ar_config, "aurarouter.fabric": ar_fabric}
        )
        try:
            cls = _import_embedded()
            backend = cls()
            result = await backend.route(
                prompt="Write a sort function", intent=RequestIntent.GENERATE_CODE
            )
        finally:
            for k, v in orig.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        assert result.routing_context is not None
        assert result.routing_context["strategy"] == "pipeline"
        assert result.routing_context["confidence_score"] == pytest.approx(0.94)
        assert result.routing_context["complexity_score"] == 2
        assert result.routing_context["hard_routed"] is False

    @pytest.mark.asyncio
    async def test_routing_context_includes_simulated_cost(self):
        """simulated_cost_avoided should be propagated when hard-routed."""
        rc = _FakeRoutingContext(hard_routed=True, simulated_cost_avoided=0.0042)
        fake_result = _FakeGenerateResult(
            text="Local response with enough content for quality check", routing_context=rc
        )

        ar = ModuleType("aurarouter")
        ar_config = ModuleType("aurarouter.config")
        ar_fabric = ModuleType("aurarouter.fabric")
        config_loader = MagicMock()
        config_loader.get_role_chain = MagicMock(return_value=["ollama:llama3:8b"])
        config_loader.get_all_model_ids = MagicMock(return_value=["ollama:llama3:8b"])
        fabric = MagicMock()
        fabric.execute = MagicMock(return_value=fake_result)
        ar_config.ConfigLoader = MagicMock(return_value=config_loader)  # type: ignore
        ar_fabric.ComputeFabric = MagicMock(return_value=fabric)  # type: ignore

        orig = {
            k: sys.modules.get(k) for k in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        }
        sys.modules.update(
            {"aurarouter": ar, "aurarouter.config": ar_config, "aurarouter.fabric": ar_fabric}
        )
        try:
            cls = _import_embedded()
            backend = cls()
            result = await backend.route(prompt="Quick sort", intent=RequestIntent.GENERATE_CODE)
        finally:
            for k, v in orig.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        assert result.routing_context is not None
        assert result.routing_context["hard_routed"] is True
        assert abs(result.routing_context["simulated_cost_avoided"] - 0.0042) < 1e-6


# ---------------------------------------------------------------------------
# T6.3: ExecutionMetadata includes routing_context
# ---------------------------------------------------------------------------


class TestExecutionMetadataRoutingContext:
    def test_routing_context_field_exists_in_metadata(self):
        meta = ExecutionMetadata()
        assert hasattr(meta, "routing_context")
        assert meta.routing_context is None

    def test_routing_context_in_execution_metadata(self):
        ctx = _make_routing_context(strategy="vector", confidence=0.95)
        meta = ExecutionMetadata(routing_context=ctx)
        assert meta.routing_context["strategy"] == "vector"
        assert meta.routing_context["confidence_score"] == pytest.approx(0.95)

    def test_execution_metadata_serializable_with_routing_context(self):
        ctx = _make_routing_context()
        meta = ExecutionMetadata(routing_context=ctx)
        dumped = meta.model_dump()
        assert dumped["routing_context"]["complexity_score"] == 2


# ---------------------------------------------------------------------------
# T6.5: OpenAI shim surfaces routing context
# ---------------------------------------------------------------------------


class TestOpenAIShimRoutingContext:
    def test_chat_response_includes_routing_context_when_present(self):
        from auracode.shim.openai_compat import _format_chat_response

        ctx = _make_routing_context(strategy="pipeline", confidence=0.92)
        meta = ExecutionMetadata(routing_context=ctx)
        engine_response = EngineResponse(
            request_id="req-001",
            content="def hello(): pass",
            model_used="ollama:llama3:8b",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
            execution_metadata=meta,
        )
        result = _format_chat_response(engine_response, "ollama:llama3:8b", "cmpl-123")
        assert "_aura_routing_context" in result
        assert result["_aura_routing_context"]["strategy"] == "pipeline"

    def test_chat_response_no_routing_context_when_absent(self):
        from auracode.shim.openai_compat import _format_chat_response

        engine_response = EngineResponse(
            request_id="req-002",
            content="hello",
            model_used="test",
            usage=TokenUsage(),
        )
        result = _format_chat_response(engine_response, "test", "cmpl-456")
        assert "_aura_routing_context" not in result

    def test_chat_response_backwards_compatible_without_metadata(self):
        from auracode.shim.openai_compat import _format_chat_response

        engine_response = EngineResponse(
            request_id="req-003",
            content="hello",
            model_used="test",
            usage=TokenUsage(),
            execution_metadata=None,
        )
        result = _format_chat_response(engine_response, "test", "cmpl-789")
        assert "id" in result
        assert "choices" in result
        assert "_aura_routing_context" not in result


# ---------------------------------------------------------------------------
# T6.6: Hard-route degradation detection
# ---------------------------------------------------------------------------


class TestHardRouteDegradationDetection:
    @pytest.mark.asyncio
    async def test_hard_route_degradation_recorded_on_empty_response(self):
        """Empty response from hard-routed local model produces DegradationNotice."""
        rc = _FakeRoutingContext(hard_routed=True, simulated_cost_avoided=0.001)
        fake_result = _FakeGenerateResult(text="", routing_context=rc)  # empty response

        ar = ModuleType("aurarouter")
        ar_config = ModuleType("aurarouter.config")
        ar_fabric = ModuleType("aurarouter.fabric")
        config_loader = MagicMock()
        config_loader.get_role_chain = MagicMock(return_value=["ollama:phi3:mini"])
        config_loader.get_all_model_ids = MagicMock(return_value=["ollama:phi3:mini"])
        fabric = MagicMock()
        fabric.execute = MagicMock(return_value=fake_result)
        ar_config.ConfigLoader = MagicMock(return_value=config_loader)  # type: ignore
        ar_fabric.ComputeFabric = MagicMock(return_value=fabric)  # type: ignore

        orig = {
            k: sys.modules.get(k) for k in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        }
        sys.modules.update(
            {"aurarouter": ar, "aurarouter.config": ar_config, "aurarouter.fabric": ar_fabric}
        )
        try:
            cls = _import_embedded()
            backend = cls()
            result = await backend.route(prompt="Hello", intent=RequestIntent.CHAT)
        finally:
            for k, v in orig.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        assert result.routing_context is not None
        assert result.routing_context["hard_routed"] is True
        # Should have a hard_routing degradation notice
        degradation_capabilities = [
            d.capability for d in result.degradations if isinstance(d, DegradationNotice)
        ]
        assert "hard_routing" in degradation_capabilities

    @pytest.mark.asyncio
    async def test_no_degradation_for_normal_hard_routed_response(self):
        """Good-quality hard-routed response does NOT produce DegradationNotice."""
        rc = _FakeRoutingContext(hard_routed=True)
        good_text = "Here is the implementation:\n\ndef hello():\n    return 'world'"
        fake_result = _FakeGenerateResult(text=good_text, routing_context=rc)

        ar = ModuleType("aurarouter")
        ar_config = ModuleType("aurarouter.config")
        ar_fabric = ModuleType("aurarouter.fabric")
        config_loader = MagicMock()
        config_loader.get_role_chain = MagicMock(return_value=["ollama:llama3:8b"])
        config_loader.get_all_model_ids = MagicMock(return_value=["ollama:llama3:8b"])
        fabric = MagicMock()
        fabric.execute = MagicMock(return_value=fake_result)
        ar_config.ConfigLoader = MagicMock(return_value=config_loader)  # type: ignore
        ar_fabric.ComputeFabric = MagicMock(return_value=fabric)  # type: ignore

        orig = {
            k: sys.modules.get(k) for k in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        }
        sys.modules.update(
            {"aurarouter": ar, "aurarouter.config": ar_config, "aurarouter.fabric": ar_fabric}
        )
        try:
            cls = _import_embedded()
            backend = cls()
            result = await backend.route(
                prompt="Write hello world", intent=RequestIntent.GENERATE_CODE
            )
        finally:
            for k, v in orig.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        hard_route_degradations = [
            d
            for d in result.degradations
            if isinstance(d, DegradationNotice) and d.capability == "hard_routing"
        ]
        assert len(hard_route_degradations) == 0


# ---------------------------------------------------------------------------
# T6.4: Grid serialization
# ---------------------------------------------------------------------------


class TestGridSerializationRoutingContext:
    def test_grid_response_to_route_result_preserves_routing_context(self):
        from auracode.grid.serializer import grid_response_to_route_result

        grid_response = MagicMock()
        grid_response.content = "grid result"
        grid_response.model_used = "grid-model"
        grid_response.prompt_tokens = 15
        grid_response.completion_tokens = 30
        grid_response.metadata = {}
        grid_response.routing_context = {
            "strategy": "pipeline",
            "confidence_score": 0.88,
            "complexity_score": 3,
            "intent": "SIMPLE_CODE",
            "hard_routed": False,
        }

        result = grid_response_to_route_result(grid_response)

        assert result.routing_context is not None
        assert result.routing_context["strategy"] == "pipeline"
        assert result.routing_context["confidence_score"] == pytest.approx(0.88)

    def test_grid_response_to_route_result_none_when_no_routing_context(self):
        from auracode.grid.serializer import grid_response_to_route_result

        grid_response = MagicMock()
        grid_response.content = "result"
        grid_response.model_used = "model"
        grid_response.prompt_tokens = 5
        grid_response.completion_tokens = 10
        grid_response.metadata = {}
        # No routing_context attribute
        del grid_response.routing_context

        result = grid_response_to_route_result(grid_response)

        assert result.routing_context is None

    def test_grid_response_routing_context_empty_dict_treated_as_none(self):
        from auracode.grid.serializer import grid_response_to_route_result

        grid_response = MagicMock()
        grid_response.content = "result"
        grid_response.model_used = "model"
        grid_response.prompt_tokens = 5
        grid_response.completion_tokens = 10
        grid_response.metadata = {}
        grid_response.routing_context = {}  # empty → falsy → None

        result = grid_response_to_route_result(grid_response)

        assert result.routing_context is None
