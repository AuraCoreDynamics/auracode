"""Tests for the real gRPC transport wiring in GridDelegateBackend.

These tests mock the generated protobuf stubs and gRPC channel to verify
that the three RPC methods correctly serialize requests and deserialize
responses via the proto layer.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from auracode.grid.client import GridDelegateBackend
from auracode.grid.messages import (
    GridRequest,
    GridResponse,
    HealthStatus,
    ModelList,
)

# ---------------------------------------------------------------------------
# Helpers — fake proto modules
# ---------------------------------------------------------------------------


def _fake_proto_modules():
    """Build fake ``auracode_grid_pb2`` and ``auracode_grid_pb2_grpc`` modules.

    The fake pb2 module provides message constructors that return
    ``SimpleNamespace`` objects, making it easy to assert field access.
    """

    pb2 = ModuleType("auracode_grid_pb2")

    def _grid_request(**kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(**kwargs)

    def _empty() -> SimpleNamespace:
        return SimpleNamespace()

    pb2.GridRequest = _grid_request  # type: ignore[attr-defined]
    pb2.Empty = _empty  # type: ignore[attr-defined]

    pb2_grpc = ModuleType("auracode_grid_pb2_grpc")

    class _FakeStub:
        def __init__(self, channel: Any) -> None:
            self.channel = channel
            self.Execute = AsyncMock()
            self.ListModels = AsyncMock()
            self.HealthCheck = AsyncMock()

    pb2_grpc.AuraCodeGridStub = _FakeStub  # type: ignore[attr-defined]

    return pb2, pb2_grpc


def _patch_generated():
    """Context manager that injects fake generated modules."""
    pb2, pb2_grpc = _fake_proto_modules()

    generated = ModuleType("auracode.grid._generated")
    generated.auracode_grid_pb2 = pb2  # type: ignore[attr-defined]
    generated.auracode_grid_pb2_grpc = pb2_grpc  # type: ignore[attr-defined]

    modules = {
        "auracode.grid._generated": generated,
        "auracode.grid._generated.auracode_grid_pb2": pb2,
        "auracode.grid._generated.auracode_grid_pb2_grpc": pb2_grpc,
    }
    return patch.dict("sys.modules", modules)


def _make_backend_with_channel(**kwargs: Any) -> tuple[GridDelegateBackend, MagicMock]:
    """Create a backend whose channel and stub are pre-configured with fakes."""
    backend = GridDelegateBackend(endpoint="localhost:50051", **kwargs)

    fake_channel = MagicMock()
    backend._channel = fake_channel

    # Build a stub with async mock RPC methods.
    stub = MagicMock()
    stub.Execute = AsyncMock()
    stub.ListModels = AsyncMock()
    stub.HealthCheck = AsyncMock()
    backend._stub = stub

    return backend, stub


# ---------------------------------------------------------------------------
# T5.2 — _call_execute
# ---------------------------------------------------------------------------


class TestCallExecute:
    """Tests for _call_execute with mocked proto stubs."""

    async def test_execute_serializes_request_fields(self) -> None:
        backend, stub = _make_backend_with_channel()

        stub.Execute.return_value = SimpleNamespace(
            request_id="r1",
            content="hello world",
            model_used="test-model",
            prompt_tokens=10,
            completion_tokens=20,
            error="",
        )

        grid_req = GridRequest(
            request_id="r1",
            intent="generate_code",
            prompt="write hello",
            context_json='{"k": "v"}',
            options={"temp": "0.5"},
        )

        with _patch_generated():
            result = await backend._call_execute(grid_req)

        assert isinstance(result, GridResponse)
        assert result.request_id == "r1"
        assert result.content == "hello world"
        assert result.model_used == "test-model"
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 20
        assert result.error == ""

    async def test_execute_passes_timeout(self) -> None:
        backend, stub = _make_backend_with_channel(timeout=45.0)

        stub.Execute.return_value = SimpleNamespace(
            request_id="r2",
            content="ok",
            model_used="m",
            prompt_tokens=0,
            completion_tokens=0,
            error="",
        )

        grid_req = GridRequest(request_id="r2", prompt="hi")

        with _patch_generated():
            await backend._call_execute(grid_req)

        # Verify timeout was passed as keyword argument.
        _, call_kwargs = stub.Execute.call_args
        assert call_kwargs["timeout"] == 45.0

    async def test_execute_propagates_error_field(self) -> None:
        backend, stub = _make_backend_with_channel()

        stub.Execute.return_value = SimpleNamespace(
            request_id="r3",
            content="",
            model_used="",
            prompt_tokens=0,
            completion_tokens=0,
            error="overloaded",
        )

        grid_req = GridRequest(request_id="r3", prompt="x")

        with _patch_generated():
            result = await backend._call_execute(grid_req)

        assert result.error == "overloaded"

    async def test_execute_raises_on_grpc_exception(self) -> None:
        backend, stub = _make_backend_with_channel()
        stub.Execute.side_effect = Exception("RPC failed")

        grid_req = GridRequest(request_id="r4", prompt="boom")

        with _patch_generated():
            with pytest.raises(Exception, match="RPC failed"):
                await backend._call_execute(grid_req)


# ---------------------------------------------------------------------------
# T5.3 — _call_list_models
# ---------------------------------------------------------------------------


class TestCallListModels:
    """Tests for _call_list_models with mocked proto stubs."""

    async def test_list_models_returns_model_list(self) -> None:
        backend, stub = _make_backend_with_channel()

        stub.ListModels.return_value = SimpleNamespace(
            models=[
                SimpleNamespace(model_id="llama3", provider="ollama", tags=["fast"]),
                SimpleNamespace(model_id="opus", provider="anthropic", tags=["smart", "expensive"]),
            ]
        )

        with _patch_generated():
            result = await backend._call_list_models()

        assert isinstance(result, ModelList)
        assert len(result.models) == 2
        assert result.models[0].model_id == "llama3"
        assert result.models[0].provider == "ollama"
        assert result.models[0].tags == ["fast"]
        assert result.models[1].model_id == "opus"
        assert "smart" in result.models[1].tags

    async def test_list_models_empty(self) -> None:
        backend, stub = _make_backend_with_channel()
        stub.ListModels.return_value = SimpleNamespace(models=[])

        with _patch_generated():
            result = await backend._call_list_models()

        assert result.models == []

    async def test_list_models_passes_timeout(self) -> None:
        backend, stub = _make_backend_with_channel(timeout=15.0)
        stub.ListModels.return_value = SimpleNamespace(models=[])

        with _patch_generated():
            await backend._call_list_models()

        _, call_kwargs = stub.ListModels.call_args
        assert call_kwargs["timeout"] == 15.0


# ---------------------------------------------------------------------------
# T5.3 — _call_health_check
# ---------------------------------------------------------------------------


class TestCallHealthCheck:
    """Tests for _call_health_check with mocked proto stubs."""

    async def test_health_check_healthy(self) -> None:
        backend, stub = _make_backend_with_channel()
        stub.HealthCheck.return_value = SimpleNamespace(healthy=True, version="2.1.0")

        with _patch_generated():
            result = await backend._call_health_check()

        assert isinstance(result, HealthStatus)
        assert result.healthy is True
        assert result.version == "2.1.0"

    async def test_health_check_unhealthy(self) -> None:
        backend, stub = _make_backend_with_channel()
        stub.HealthCheck.return_value = SimpleNamespace(healthy=False, version="0.0.1")

        with _patch_generated():
            result = await backend._call_health_check()

        assert result.healthy is False

    async def test_health_check_passes_timeout(self) -> None:
        backend, stub = _make_backend_with_channel(timeout=5.0)
        stub.HealthCheck.return_value = SimpleNamespace(healthy=True, version="1.0")

        with _patch_generated():
            await backend._call_health_check()

        _, call_kwargs = stub.HealthCheck.call_args
        assert call_kwargs["timeout"] == 5.0


# ---------------------------------------------------------------------------
# T5.4 — _ensure_channel
# ---------------------------------------------------------------------------


class TestEnsureChannelStubCreation:
    """Tests that _ensure_channel creates and caches the gRPC stub."""

    def test_ensure_channel_creates_stub_when_generated_available(self) -> None:
        """When generated stubs are importable, _stub should be a proper stub."""
        backend = GridDelegateBackend(endpoint="localhost:50051")

        fake_grpc = MagicMock()
        fake_grpc_aio = MagicMock()
        fake_grpc.aio = fake_grpc_aio
        fake_channel = MagicMock()
        fake_grpc_aio.insecure_channel.return_value = fake_channel

        fake_stub_class = MagicMock()
        fake_stub_instance = MagicMock()
        fake_stub_class.return_value = fake_stub_instance

        pb2_grpc = ModuleType("auracode_grid_pb2_grpc")
        pb2_grpc.AuraCodeGridStub = fake_stub_class  # type: ignore[attr-defined]

        # The `from auracode.grid._generated import auracode_grid_pb2_grpc`
        # statement resolves by looking up the parent module and accessing the
        # attribute.  We need the parent mock to expose our pb2_grpc module.
        generated_pkg = MagicMock()
        generated_pkg.auracode_grid_pb2_grpc = pb2_grpc

        with patch.dict(
            "sys.modules",
            {
                "grpc": fake_grpc,
                "grpc.aio": fake_grpc_aio,
                "auracode.grid._generated": generated_pkg,
                "auracode.grid._generated.auracode_grid_pb2_grpc": pb2_grpc,
            },
        ):
            backend._ensure_channel()

        assert backend._channel is fake_channel
        fake_stub_class.assert_called_once_with(fake_channel)
        assert backend._stub is fake_stub_instance

    def test_ensure_channel_falls_back_when_generated_missing(self) -> None:
        """When generated stubs are NOT importable, _stub == _channel."""
        backend = GridDelegateBackend(endpoint="localhost:50051")

        fake_grpc = MagicMock()
        fake_grpc_aio = MagicMock()
        fake_grpc.aio = fake_grpc_aio
        fake_channel = MagicMock()
        fake_grpc_aio.insecure_channel.return_value = fake_channel

        # Do NOT inject the _generated modules — let the import fail.
        with patch.dict(
            "sys.modules",
            {
                "grpc": fake_grpc,
                "grpc.aio": fake_grpc_aio,
            },
        ):
            # Remove any cached _generated module.
            sys.modules.pop("auracode.grid._generated", None)
            sys.modules.pop("auracode.grid._generated.auracode_grid_pb2_grpc", None)
            backend._ensure_channel()

        assert backend._channel is fake_channel
        assert backend._stub is fake_channel

    def test_ensure_channel_no_op_when_already_open(self) -> None:
        """Second call to _ensure_channel should not recreate the channel."""
        backend = GridDelegateBackend(endpoint="localhost:50051")
        sentinel_channel = object()
        sentinel_stub = object()
        backend._channel = sentinel_channel
        backend._stub = sentinel_stub

        backend._ensure_channel()

        assert backend._channel is sentinel_channel
        assert backend._stub is sentinel_stub


# ---------------------------------------------------------------------------
# Graceful error when grpcio is not installed
# ---------------------------------------------------------------------------


class TestGrpcioMissing:
    """Verify helpful error when grpcio is not installed."""

    def test_import_error_message(self) -> None:
        backend = GridDelegateBackend(endpoint="localhost:50051")

        # Remove grpc from sys.modules and make import fail.
        with patch.dict("sys.modules", {"grpc": None, "grpc.aio": None}):
            with pytest.raises(ImportError, match="grpcio is required"):
                backend._ensure_channel()
