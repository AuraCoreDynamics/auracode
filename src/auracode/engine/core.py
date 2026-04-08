"""AuraCodeEngine — central orchestrator."""

from __future__ import annotations

from collections.abc import AsyncIterator

import structlog

from auracode.engine.session import SessionManager
from auracode.models.config import AuraCodeConfig
from auracode.models.context import SessionContext
from auracode.models.normalization import normalize_options_to_policy
from auracode.models.request import (
    DegradationNotice,
    EngineRequest,
    EngineResponse,
    ExecutionMetadata,
    ExecutionMode,
)
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
            # Resolve effective execution policy: typed wins, legacy fills gaps.
            effective_policy = request.execution_policy
            if request.options:
                effective_policy, _ignored = normalize_options_to_policy(
                    request.options, base=request.execution_policy
                )

            route_options = dict(request.options or {})
            route_options["_execution_policy"] = effective_policy.model_dump()
            # Pass local permissions to router (Task 2.2)
            route_options["permissions"] = self.config.permissions.model_dump()

            # --- Agentic Loop (Task 3.1) ---
            if effective_policy.mode == ExecutionMode.MONOLOGUE:
                # Monologue mode is handled as a single (but long) call
                # to aurarouter's monologue orchestrator
                pass

            # If we wanted a local agentic loop in auracode, we'd implement it here.
            # For now, we delegate the reasoning loop to aurarouter but we could
            # add a multi-turn loop here if the model returns tool calls that
            # aurarouter doesn't handle.

            # Clear journal before execution
            if hasattr(self, "_journal"):
                self._journal.entries.clear()

            route_result = await self.router.route(
                prompt=request.prompt,
                intent=request.intent,
                context=session,
                options=route_options,
            )

            # Collect journal (Task 2.3)
            journal_entries = []
            if hasattr(self, "_journal"):
                journal_entries = self._journal.to_dict()

            # Build execution metadata from backend result.
            exec_meta = self._extract_execution_metadata(route_result)

            response = EngineResponse(
                request_id=request.request_id,
                content=route_result.content,
                model_used=route_result.model_used,
                usage=route_result.usage,
                execution_metadata=exec_meta,
            )
        except Exception as exc:
            log.error("engine.execute.failed", request_id=request.request_id, error=str(exc))
            response = EngineResponse(
                request_id=request.request_id,
                content="",
                error=str(exc),
            )
            journal_entries = []

        # Update session history
        self.session_manager.update(session.session_id, request, response, journal=journal_entries)
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
            # Resolve effective execution policy for streaming.
            effective_policy = request.execution_policy
            if request.options:
                effective_policy, _ignored = normalize_options_to_policy(
                    request.options, base=request.execution_policy
                )

            route_options = dict(request.options or {})
            route_options["_execution_policy"] = effective_policy.model_dump()
            # Pass local permissions to router (Task 2.2)
            route_options["permissions"] = self.config.permissions.model_dump()

            # Clear journal before execution
            if hasattr(self, "_journal"):
                self._journal.entries.clear()

            async for chunk in self.router.route_stream(
                prompt=request.prompt,
                intent=request.intent,
                context=session,
                options=route_options,
            ):
                collected.append(chunk)
                yield chunk
        except Exception as exc:
            log.error("engine.execute_stream.failed", request_id=request.request_id, error=str(exc))
            raise

        # Collect journal (Task 2.3)
        journal_entries = []
        if hasattr(self, "_journal"):
            journal_entries = self._journal.to_dict()

        # Update session history with the complete response.
        full_content = "".join(collected)

        # Attempt to retrieve metadata from the stream.
        exec_meta = None
        stream_result = self.router.get_last_stream_result()
        if stream_result is not None:
            exec_meta = self._extract_execution_metadata(stream_result)

        response = EngineResponse(
            request_id=request.request_id,
            content=full_content,
            execution_metadata=exec_meta,
        )
        self.session_manager.update(session.session_id, request, response, journal=journal_entries)

    def get_session(self, session_id: str) -> SessionContext | None:
        """Retrieve a session by ID."""
        return self.session_manager.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close and discard a session."""
        self.session_manager.close(session_id)

    async def get_budget_status(self) -> dict:
        """Return the current budget status from the router."""
        try:
            # This requires an MCP tool or direct call if embedded
            if hasattr(self.router, "get_budget_status"):
                return await self.router.get_budget_status()

            # Fallback for MCP-based routers: call a tool if it exists
            # (Pending: add aurarouter.budget.status MCP tool)
            return {"error": "Budget status not supported by current router"}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _extract_execution_metadata(route_result) -> ExecutionMetadata | None:
        """Build ExecutionMetadata from a RouteResult if metadata is present."""
        meta = route_result.metadata
        if not meta and not getattr(route_result, "degradations", None):
            return None

        degradation_notices: list[DegradationNotice] = []
        raw_degradations = getattr(route_result, "degradations", []) or meta.get("degradations", [])
        for d in raw_degradations:
            if isinstance(d, DegradationNotice):
                degradation_notices.append(d)
            elif isinstance(d, dict):
                try:
                    degradation_notices.append(DegradationNotice(**d))
                except Exception:
                    pass

        return ExecutionMetadata(
            analyzer_used=meta.get("analyzer_used"),
            execution_mode_used=meta.get("execution_mode_used"),
            sovereignty_outcome=meta.get("sovereignty_outcome"),
            retrieval_summary=meta.get("retrieval_summary"),
            trace_id=meta.get("trace_id"),
            verification_outcome=meta.get("verification_outcome"),
            degradations=degradation_notices,
            backend_warnings=meta.get("backend_warnings", []),
            routing_context=getattr(route_result, "routing_context", None),
        )
