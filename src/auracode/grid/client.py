"""gRPC-based routing backend that delegates to AuraGrid."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from auracode.grid.messages import (
    GridResponse,
    HealthStatus,
    ModelEntry,
    ModelList,
)
from auracode.grid.serializer import (
    engine_request_to_grid,
    grid_response_to_route_result,
)
from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult

logger = logging.getLogger(__name__)


class GridConnectionError(Exception):
    """Raised when the grid endpoint is unreachable."""


class GridRpcError(Exception):
    """Raised when a gRPC call returns an error status."""


class GridDelegateBackend(BaseRouterBackend):
    """Router backend that delegates inference to an AuraGrid cluster via gRPC.

    Parameters
    ----------
    endpoint:
        ``host:port`` of the AuraGrid gRPC service.
    timeout:
        Per-call timeout in seconds (default 30).
    tls_cert:
        Path to a client TLS certificate (mTLS).
    tls_key:
        Path to the client private key (mTLS).
    ca_cert:
        Path to a CA certificate for server verification.
    """

    def __init__(
        self,
        endpoint: str,
        timeout: float = 30.0,
        tls_cert: str | None = None,
        tls_key: str | None = None,
        ca_cert: str | None = None,
        server_name: str | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._tls_cert = tls_cert
        self._tls_key = tls_key
        self._ca_cert = ca_cert
        self._server_name = server_name
        self._channel: Any = None
        self._stub: Any = None

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def _ensure_channel(self) -> None:
        """Lazily create a gRPC channel and stub.

        This imports ``grpc`` at call-time so the rest of the module stays
        importable without grpcio installed (pure-Python message classes are
        used for serialisation).
        """
        if self._channel is not None:
            return

        try:
            import grpc  # type: ignore[import-untyped]
            import grpc.aio  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "grpcio is required for GridDelegateBackend. "
                "Install it with: pip install auracode[grid]"
            ) from exc

        if self._ca_cert or (self._tls_cert and self._tls_key):
            # Load CA certificate for server verification (custom CA or system default)
            root_certificates: bytes | None = None
            if self._ca_cert:
                try:
                    with open(self._ca_cert, "rb") as f:
                        root_certificates = f.read()
                except OSError as exc:
                    from auracode.errors import AuraError

                    raise GridConnectionError(
                        AuraError(
                            error_code=4010,
                            category="auth",
                            message="Failed to load grid CA certificate",
                            detail=str(exc),
                            source_project="auracode",
                        ).model_dump_json()
                    ) from exc

            # Load client cert + key for mTLS when both are provided
            private_key: bytes | None = None
            certificate_chain: bytes | None = None
            if self._tls_cert and self._tls_key:
                try:
                    with open(self._tls_cert, "rb") as f:
                        certificate_chain = f.read()
                    with open(self._tls_key, "rb") as f:
                        private_key = f.read()
                except OSError as exc:
                    from auracode.errors import AuraError

                    raise GridConnectionError(
                        AuraError(
                            error_code=4010,
                            category="auth",
                            message="Failed to load grid client certificate or key",
                            detail=str(exc),
                            source_project="auracode",
                        ).model_dump_json()
                    ) from exc

            creds = grpc.ssl_channel_credentials(
                root_certificates=root_certificates,
                private_key=private_key,
                certificate_chain=certificate_chain,
            )
            options: list[tuple[str, str]] = []
            if self._server_name:
                options.append(("grpc.ssl_target_name_override", self._server_name))
            if options:
                self._channel = grpc.aio.secure_channel(self._endpoint, creds, options=options)
            else:
                self._channel = grpc.aio.secure_channel(self._endpoint, creds)
        else:
            self._channel = grpc.aio.insecure_channel(self._endpoint)

        try:
            from auracode.grid._generated import (
                auracode_grid_pb2_grpc,  # type: ignore[import-untyped]
            )
        except ImportError:
            # Generated stubs not available — stub will remain as the channel
            # so that existing mock-based tests keep working.
            self._stub = self._channel
            return

        self._stub = auracode_grid_pb2_grpc.AuraCodeGridStub(self._channel)

    # ------------------------------------------------------------------
    # BaseRouterBackend interface
    # ------------------------------------------------------------------

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        """Serialize to GridRequest, call Execute, return RouteResult."""
        request_id = uuid.uuid4().hex
        grid_req = engine_request_to_grid(
            request_id=request_id,
            prompt=prompt,
            intent=intent,
            context=context,
            options=options,
        )

        grid_resp = await self._call_execute(grid_req)

        if grid_resp.error:
            raise GridRpcError(grid_resp.error)

        return grid_response_to_route_result(grid_resp)

    async def list_models(self) -> list[ModelInfo]:
        """Call ListModels on the grid and return ModelInfo list."""
        model_list = await self._call_list_models()
        return [
            ModelInfo(
                model_id=entry.model_id,
                provider=entry.provider,
                tags=list(entry.tags),
            )
            for entry in model_list.models
        ]

    async def health_check(self) -> bool:
        """Call HealthCheck on the grid endpoint."""
        try:
            status = await self._call_health_check()
            return status.healthy
        except Exception:
            logger.debug("Grid health check failed", exc_info=True)
            return False

    def close(self) -> None:
        """Close the underlying gRPC channel."""
        if self._channel is not None:
            self._channel.close()
            self._channel = None
            self._stub = None

    # ------------------------------------------------------------------
    # Internal RPC helpers — thin wrappers that are easy to mock
    # ------------------------------------------------------------------

    async def _call_execute(self, grid_request: Any) -> GridResponse:
        """Invoke the Execute RPC.  Override or mock in tests."""
        self._ensure_channel()
        from auracode.grid._generated import auracode_grid_pb2  # type: ignore[import-untyped]

        proto_req = auracode_grid_pb2.GridRequest(
            request_id=grid_request.request_id,
            intent=grid_request.intent,
            prompt=grid_request.prompt,
            context_json=grid_request.context_json,
            options=grid_request.options,
        )
        proto_resp = await self._stub.Execute(proto_req, timeout=self._timeout)
        return GridResponse(
            request_id=proto_resp.request_id,
            content=proto_resp.content,
            model_used=proto_resp.model_used,
            prompt_tokens=proto_resp.prompt_tokens,
            completion_tokens=proto_resp.completion_tokens,
            error=proto_resp.error,
        )

    async def _call_list_models(self) -> ModelList:
        """Invoke the ListModels RPC."""
        self._ensure_channel()
        from auracode.grid._generated import auracode_grid_pb2  # type: ignore[import-untyped]

        proto_resp = await self._stub.ListModels(auracode_grid_pb2.Empty(), timeout=self._timeout)
        return ModelList(
            models=[
                ModelEntry(
                    model_id=m.model_id,
                    provider=m.provider,
                    tags=list(m.tags),
                )
                for m in proto_resp.models
            ]
        )

    async def _call_health_check(self) -> HealthStatus:
        """Invoke the HealthCheck RPC."""
        self._ensure_channel()
        from auracode.grid._generated import auracode_grid_pb2  # type: ignore[import-untyped]

        proto_resp = await self._stub.HealthCheck(auracode_grid_pb2.Empty(), timeout=self._timeout)
        return HealthStatus(
            healthy=proto_resp.healthy,
            version=proto_resp.version,
        )
