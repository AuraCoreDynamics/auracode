"""Tests for GridDelegateBackend — all gRPC interactions are mocked."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from auracode.grid.client import GridDelegateBackend, GridRpcError
from auracode.grid.messages import GridResponse, HealthStatus, ModelEntry, ModelList
from auracode.models.request import RequestIntent
from auracode.routing.base import ModelInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_backend(**kwargs: Any) -> GridDelegateBackend:
    """Create a backend with mocked internals so grpcio is not needed."""
    backend = GridDelegateBackend(endpoint="localhost:50051", **kwargs)
    return backend


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRoute:
    async def test_route_returns_route_result(self) -> None:
        backend = _make_backend()
        backend._call_execute = AsyncMock(  # type: ignore[assignment]
            return_value=GridResponse(
                request_id="r1",
                content="Generated code",
                model_used="grid-llm",
                prompt_tokens=5,
                completion_tokens=10,
            )
        )

        result = await backend.route("write code", RequestIntent.GENERATE_CODE)
        assert result.content == "Generated code"
        assert result.model_used == "grid-llm"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 5

    async def test_route_propagates_error_field(self) -> None:
        backend = _make_backend()
        backend._call_execute = AsyncMock(  # type: ignore[assignment]
            return_value=GridResponse(
                request_id="r2",
                content="",
                model_used="",
                error="model overloaded",
            )
        )

        with pytest.raises(GridRpcError, match="model overloaded"):
            await backend.route("hi", RequestIntent.CHAT)

    async def test_route_passes_context_and_options(self) -> None:
        from auracode.models.context import SessionContext

        backend = _make_backend()
        captured: list[Any] = []

        async def _capture(grid_req: Any) -> GridResponse:
            captured.append(grid_req)
            return GridResponse(content="ok", model_used="m")

        backend._call_execute = _capture  # type: ignore[assignment]

        ctx = SessionContext(session_id="s", working_directory="/tmp")
        await backend.route("q", RequestIntent.CHAT, context=ctx, options={"k": "v"})

        assert len(captured) == 1
        assert captured[0].context_json != ""
        assert captured[0].options == {"k": "v"}

    async def test_route_connection_failure(self) -> None:
        backend = _make_backend()
        backend._call_execute = AsyncMock(  # type: ignore[assignment]
            side_effect=ConnectionError("unreachable")
        )

        with pytest.raises(ConnectionError):
            await backend.route("hi", RequestIntent.CHAT)


class TestListModels:
    async def test_returns_model_info_list(self) -> None:
        backend = _make_backend()
        backend._call_list_models = AsyncMock(  # type: ignore[assignment]
            return_value=ModelList(
                models=[
                    ModelEntry(model_id="llama3", provider="ollama", tags=["fast"]),
                    ModelEntry(model_id="claude", provider="anthropic", tags=["smart"]),
                ]
            )
        )

        models = await backend.list_models()
        assert len(models) == 2
        assert models[0].model_id == "llama3"
        assert models[1].provider == "anthropic"
        assert "smart" in models[1].tags


class TestHealthCheck:
    async def test_healthy(self) -> None:
        backend = _make_backend()
        backend._call_health_check = AsyncMock(  # type: ignore[assignment]
            return_value=HealthStatus(healthy=True, version="1.0")
        )
        assert await backend.health_check() is True

    async def test_unhealthy(self) -> None:
        backend = _make_backend()
        backend._call_health_check = AsyncMock(  # type: ignore[assignment]
            return_value=HealthStatus(healthy=False, version="1.0")
        )
        assert await backend.health_check() is False

    async def test_exception_returns_false(self) -> None:
        backend = _make_backend()
        backend._call_health_check = AsyncMock(  # type: ignore[assignment]
            side_effect=ConnectionError("down")
        )
        assert await backend.health_check() is False


class TestClose:
    def test_close_resets_channel(self) -> None:
        from unittest.mock import MagicMock

        backend = _make_backend()
        # Simulate an open channel.
        backend._channel = MagicMock()
        backend._stub = object()
        backend.close()
        assert backend._channel is None
        assert backend._stub is None


class TestTlsAndTimeout:
    """Tests for TLS credential setup and timeout configuration."""

    def test_default_timeout_is_30(self) -> None:
        backend = _make_backend()
        assert backend._timeout == 30.0

    def test_custom_timeout_stored(self) -> None:
        backend = _make_backend(timeout=60.0)
        assert backend._timeout == 60.0

    def test_tls_params_stored(self) -> None:
        backend = GridDelegateBackend(
            endpoint="grid.example.com:443",
            tls_cert="/path/to/cert.pem",
            tls_key="/path/to/key.pem",
            ca_cert="/path/to/ca.pem",
        )
        assert backend._tls_cert == "/path/to/cert.pem"
        assert backend._tls_key == "/path/to/key.pem"
        assert backend._ca_cert == "/path/to/ca.pem"

    def test_ensure_channel_tls_creates_secure_channel(self, tmp_path) -> None:
        """With TLS params and real files, _ensure_channel creates a secure channel."""
        from unittest.mock import MagicMock

        cert_file = tmp_path / "cert.pem"
        key_file = tmp_path / "key.pem"
        ca_file = tmp_path / "ca.pem"
        cert_file.write_bytes(b"CERT_DATA")
        key_file.write_bytes(b"KEY_DATA")
        ca_file.write_bytes(b"CA_DATA")

        backend = GridDelegateBackend(
            endpoint="grid:443",
            tls_cert=str(cert_file),
            tls_key=str(key_file),
            ca_cert=str(ca_file),
        )

        fake_grpc = MagicMock()
        fake_grpc_aio = MagicMock()
        fake_creds = MagicMock()
        fake_grpc.ssl_channel_credentials.return_value = fake_creds
        fake_grpc.aio = fake_grpc_aio

        with patch.dict("sys.modules", {"grpc": fake_grpc, "grpc.aio": fake_grpc_aio}):
            backend._ensure_channel()

        fake_grpc.ssl_channel_credentials.assert_called_once_with(
            root_certificates=b"CA_DATA",
            private_key=b"KEY_DATA",
            certificate_chain=b"CERT_DATA",
        )
        fake_grpc_aio.secure_channel.assert_called_once_with("grid:443", fake_creds)
        assert backend._channel is not None

    def test_ensure_channel_insecure_without_tls(self) -> None:
        """Without TLS params, _ensure_channel creates an insecure channel."""
        from unittest.mock import MagicMock

        backend = _make_backend()

        fake_grpc = MagicMock()
        fake_grpc_aio = MagicMock()
        fake_grpc.aio = fake_grpc_aio

        with patch.dict("sys.modules", {"grpc": fake_grpc, "grpc.aio": fake_grpc_aio}):
            backend._ensure_channel()

        fake_grpc_aio.insecure_channel.assert_called_once_with("localhost:50051")
        assert backend._channel is not None


