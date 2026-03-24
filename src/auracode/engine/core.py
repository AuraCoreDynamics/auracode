"""AuraCodeEngine — central orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

from auracode.engine.session import SessionManager
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.request import EngineRequest, EngineResponse
from auracode.routing.base import BaseRouterBackend

log = structlog.get_logger()


class AuraCodeEngine:
    """Core engine that ties routing, sessions, and adapters together."""

    def __init__(self, config: AuraCodeConfig, router: BaseRouterBackend) -> None:
        self.config = config
        self.router = router
        self.session_manager = SessionManager()

    async def execute(self, request: EngineRequest) -> EngineResponse:
        """Process an EngineRequest end-to-end.

        1. Resolve or create a session.
        2. Delegate to the router backend.
        3. Wrap the result in an EngineResponse.
        4. Update the session history.
        """
        # Resolve session
        session: SessionContext | None = None
        if request.context is not None:
            session = self.session_manager.get(request.context.session_id)
        if session is None:
            session = self.session_manager.create(working_directory=".")

        log.info(
            "engine.execute",
            request_id=request.request_id,
            intent=request.intent.value,
            session_id=session.session_id,
        )

        try:
            route_result = await self.router.route(
                prompt=request.prompt,
                intent=request.intent,
                context=session,
                options=request.options or None,
            )

            response = EngineResponse(
                request_id=request.request_id,
                content=route_result.content,
                model_used=route_result.model_used,
                usage=route_result.usage,
            )
        except Exception as exc:
            log.error("engine.execute.failed", request_id=request.request_id, error=str(exc))
            response = EngineResponse(
                request_id=request.request_id,
                content="",
                error=str(exc),
            )

        # Update session history
        self.session_manager.update(session.session_id, request, response)
        return response

    async def execute_stream(self, request: EngineRequest) -> AsyncIterator[str]:
        """Stream response tokens for an EngineRequest.

        Yields string chunks as they arrive from the router backend.
        Session resolution and history update are handled identically
        to :meth:`execute`.
        """
        # Resolve session
        session: SessionContext | None = None
        if request.context is not None:
            session = self.session_manager.get(request.context.session_id)
        if session is None:
            session = self.session_manager.create(working_directory=".")

        log.info(
            "engine.execute_stream",
            request_id=request.request_id,
            intent=request.intent.value,
            session_id=session.session_id,
        )

        collected: list[str] = []
        try:
            async for chunk in self.router.route_stream(
                prompt=request.prompt,
                intent=request.intent,
                context=session,
                options=request.options or None,
            ):
                collected.append(chunk)
                yield chunk
        except Exception as exc:
            log.error("engine.execute_stream.failed", request_id=request.request_id, error=str(exc))
            raise

        # Update session history with the complete response.
        full_content = "".join(collected)
        response = EngineResponse(
            request_id=request.request_id,
            content=full_content,
        )
        self.session_manager.update(session.session_id, request, response)

    def get_session(self, session_id: str) -> SessionContext | None:
        """Retrieve a session by ID."""
        return self.session_manager.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close and discard a session."""
        self.session_manager.close(session_id)
