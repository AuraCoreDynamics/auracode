"""Tests for FailoverBackend."""

from __future__ import annotations

from auracode.grid.failover import FailoverBackend
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import ModelInfo

from .conftest import MockBackend


class TestRouteFailover:
    async def test_primary_healthy_and_under_threshold(
        self, healthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(healthy_primary, healthy_fallback, context_threshold=100_000)
        result = await fo.route("short prompt", RequestIntent.CHAT)

        assert result.content == "primary answer"
        assert len(healthy_primary.route_calls) == 1
        assert len(healthy_fallback.route_calls) == 0

    async def test_primary_fails_uses_fallback(
        self, failing_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(failing_primary, healthy_fallback)
        result = await fo.route("prompt", RequestIntent.CHAT)

        assert result.content == "fallback answer"
        assert len(failing_primary.route_calls) == 1
        assert len(healthy_fallback.route_calls) == 1

    async def test_primary_unhealthy_skips_to_fallback(
        self, unhealthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(unhealthy_primary, healthy_fallback)
        result = await fo.route("prompt", RequestIntent.CHAT)

        assert result.content == "fallback answer"
        assert len(unhealthy_primary.route_calls) == 0
        assert len(healthy_fallback.route_calls) == 1

    async def test_over_threshold_uses_primary_first(
        self, healthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(healthy_primary, healthy_fallback, context_threshold=10)
        # A big prompt that exceeds the threshold (10 tokens ~ 40 chars).
        big_prompt = "x" * 200
        result = await fo.route(big_prompt, RequestIntent.CHAT)

        # FIXED: Over-threshold now prefers primary (grid) since large
        # requests benefit from distributed compute.
        assert result.content == "primary answer"
        assert len(healthy_primary.route_calls) == 1

    async def test_context_size_counted(
        self, healthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(healthy_primary, healthy_fallback, context_threshold=50)
        ctx = SessionContext(
            session_id="s",
            working_directory="/tmp",
            files=[FileContext(path="big.py", content="a" * 1000)],
        )
        result = await fo.route("hi", RequestIntent.CHAT, context=ctx)

        # FIXED: Over-threshold prefers primary (grid).
        assert result.content == "primary answer"

    async def test_health_check_error_falls_back(self, healthy_fallback: MockBackend) -> None:
        primary = MockBackend(health_error=ConnectionError("timeout"))
        fo = FailoverBackend(primary, healthy_fallback)
        result = await fo.route("prompt", RequestIntent.CHAT)

        assert result.content == "fallback answer"


class TestListModels:
    async def test_merges_and_deduplicates(
        self, healthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        # Add a shared model to both.
        shared = ModelInfo(model_id="shared", provider="both", tags=[])
        healthy_primary.models.append(shared)
        healthy_fallback.models.append(shared)

        fo = FailoverBackend(healthy_primary, healthy_fallback)
        models = await fo.list_models()

        ids = [m.model_id for m in models]
        assert ids.count("shared") == 1
        assert "grid-model" in ids
        assert "local-model" in ids

    async def test_primary_list_failure_still_returns_fallback(
        self, healthy_fallback: MockBackend
    ) -> None:
        primary = MockBackend(healthy=True)

        # Override list_models to raise.
        async def _boom() -> list[ModelInfo]:
            raise RuntimeError("list failed")

        primary.list_models = _boom  # type: ignore[assignment]

        fo = FailoverBackend(primary, healthy_fallback)
        models = await fo.list_models()
        assert len(models) == 1
        assert models[0].model_id == "local-model"


class TestHealthCheck:
    async def test_true_if_primary_healthy(
        self, healthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(healthy_primary, healthy_fallback)
        assert await fo.health_check() is True

    async def test_true_if_only_fallback_healthy(
        self, unhealthy_primary: MockBackend, healthy_fallback: MockBackend
    ) -> None:
        fo = FailoverBackend(unhealthy_primary, healthy_fallback)
        assert await fo.health_check() is True

    async def test_false_if_both_unhealthy(self) -> None:
        p = MockBackend(healthy=False)
        f = MockBackend(healthy=False)
        fo = FailoverBackend(p, f)
        assert await fo.health_check() is False

    async def test_true_if_primary_errors_but_fallback_healthy(
        self, healthy_fallback: MockBackend
    ) -> None:
        primary = MockBackend(health_error=RuntimeError("boom"))
        fo = FailoverBackend(primary, healthy_fallback)
        assert await fo.health_check() is True
