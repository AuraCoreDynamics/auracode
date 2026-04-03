"""Failover backend that tries a primary backend then falls back."""

from __future__ import annotations

import logging
from typing import Any

from auracode.models.context import SessionContext
from auracode.models.request import (
    DegradationNotice,
    RequestIntent,
    RoutingPreference,
)
from auracode.routing.base import (
    AnalyzerInfo,
    BaseRouterBackend,
    ModelInfo,
    RouteResult,
    ServiceInfo,
)

logger = logging.getLogger(__name__)


class FailoverBackend(BaseRouterBackend):
    """Tries *primary*; on failure (or context-size threshold) uses *fallback*.

    Parameters
    ----------
    primary:
        The preferred backend (e.g. ``GridDelegateBackend``).
    fallback:
        The local/secondary backend to use when *primary* is unavailable.
    context_threshold:
        If the estimated token count of prompt + context exceeds this value
        the request is sent directly to *fallback* without trying *primary*.
    """

    def __init__(
        self,
        primary: BaseRouterBackend,
        fallback: BaseRouterBackend,
        context_threshold: int = 100_000,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._threshold = context_threshold

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_tokens(prompt: str, context: SessionContext | None) -> int:
        """Rough token estimate: ~4 characters per token."""
        total_chars = len(prompt)
        if context is not None:
            for f in context.files:
                if f.content:
                    total_chars += len(f.content)
            for entry in context.history:
                for v in entry.values():
                    total_chars += len(v)
        return total_chars // 4

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
        # Extract routing preference from policy if available.
        policy_dict = (
            (options or {}).get("_execution_policy")
            or (options or {}).get("execution_policy")
            or {}
        )
        routing_pref = (
            RoutingPreference(policy_dict.get("routing", "auto"))
            if policy_dict
            else RoutingPreference.AUTO
        )

        # Sovereignty enforcement: if enforce + no cloud, force local.
        sov = policy_dict.get("sovereignty", {}) if policy_dict else {}
        if sov.get("enforcement") == "enforce" and not sov.get("allow_cloud", True):
            if routing_pref == RoutingPreference.REQUIRE_GRID:
                raise RuntimeError(
                    "Conflict: sovereignty policy forbids cloud execution "
                    "but routing requires grid."
                )
            logger.info("Sovereignty enforces local-only; routing to fallback.")
            return await self._fallback.route(prompt, intent, context, options)

        # Hard requirements: routing policy overrides threshold logic.
        if routing_pref == RoutingPreference.REQUIRE_GRID:
            return await self._route_require_primary(prompt, intent, context, options)
        if routing_pref == RoutingPreference.REQUIRE_LOCAL:
            return await self._fallback.route(prompt, intent, context, options)

        estimated = self._estimate_tokens(prompt, context)

        # FIXED: Large requests should PREFER primary (Grid), not bypass it.
        # Over-threshold = request is too large for local, send to Grid.
        if estimated > self._threshold:
            logger.info(
                "Estimated tokens (%d) exceed threshold (%d); preferring primary (grid).",
                estimated,
                self._threshold,
            )
            try:
                primary_healthy = await self._primary.health_check()
                if primary_healthy:
                    return await self._primary.route(prompt, intent, context, options)
            except Exception:
                logger.warning(
                    "Primary route failed for over-threshold request; falling back.", exc_info=True
                )
            # If primary not available, fall back but record degradation.
            result = await self._fallback.route(prompt, intent, context, options)
            return RouteResult(
                content=result.content,
                model_used=result.model_used,
                usage=result.usage,
                metadata=result.metadata,
                degradations=list(result.degradations)
                + [
                    DegradationNotice(
                        capability="routing",
                        requested="prefer_grid",
                        actual="fallback_local",
                        reason=f"Grid unavailable for large request ({estimated} est. tokens).",
                    )
                ],
            )

        # Under threshold: prefer based on routing pref or default order.
        if routing_pref == RoutingPreference.PREFER_GRID:
            return await self._try_primary_then_fallback(prompt, intent, context, options)

        # Default: try primary if healthy, else fallback.
        return await self._try_primary_then_fallback(prompt, intent, context, options)

    async def _route_require_primary(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None,
        options: dict[str, Any] | None,
    ) -> RouteResult:
        """Route with require_grid — no silent fallback."""
        primary_healthy = False
        try:
            primary_healthy = await self._primary.health_check()
        except Exception:
            pass
        if not primary_healthy:
            raise RuntimeError(
                "Grid execution required by policy but primary backend is unavailable."
            )
        return await self._primary.route(prompt, intent, context, options)

    async def _try_primary_then_fallback(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None,
        options: dict[str, Any] | None,
    ) -> RouteResult:
        """Try primary, fall back on failure."""
        primary_healthy = False
        try:
            primary_healthy = await self._primary.health_check()
        except Exception:
            logger.debug("Primary health check raised", exc_info=True)

        if not primary_healthy:
            logger.info("Primary unhealthy; routing to fallback.")
            return await self._fallback.route(prompt, intent, context, options)

        try:
            result = await self._primary.route(prompt, intent, context, options)
            logger.debug("Primary backend succeeded.")
            return result
        except Exception:
            logger.warning("Primary route failed; falling back.", exc_info=True)
            return await self._fallback.route(prompt, intent, context, options)

    async def list_models(self) -> list[ModelInfo]:
        """Merge models from both backends, deduplicate by model_id."""
        seen: dict[str, ModelInfo] = {}

        for backend in (self._primary, self._fallback):
            try:
                models = await backend.list_models()
                for m in models:
                    if m.model_id not in seen:
                        seen[m.model_id] = m
            except Exception:
                logger.debug("list_models failed for %s", type(backend).__name__, exc_info=True)

        return list(seen.values())

    async def health_check(self) -> bool:
        """Return True if *either* backend is healthy."""
        for backend in (self._primary, self._fallback):
            try:
                if await backend.health_check():
                    return True
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Catalog methods — merge / delegate pattern
    # ------------------------------------------------------------------

    async def list_services(self) -> list[ServiceInfo]:
        """Merge services from both backends, deduplicate by service_id."""
        seen: dict[str, ServiceInfo] = {}
        for backend in (self._primary, self._fallback):
            try:
                services = await backend.list_services()
                for s in services:
                    if s.service_id not in seen:
                        seen[s.service_id] = s
            except Exception:
                logger.debug(
                    "list_services failed for %s",
                    type(backend).__name__,
                    exc_info=True,
                )
        return list(seen.values())

    async def list_analyzers(self) -> list[AnalyzerInfo]:
        """Merge analyzers from both backends, deduplicate by analyzer_id."""
        seen: dict[str, AnalyzerInfo] = {}
        for backend in (self._primary, self._fallback):
            try:
                analyzers = await backend.list_analyzers()
                for a in analyzers:
                    if a.analyzer_id not in seen:
                        seen[a.analyzer_id] = a
            except Exception:
                logger.debug(
                    "list_analyzers failed for %s",
                    type(backend).__name__,
                    exc_info=True,
                )
        return list(seen.values())

    async def get_active_analyzer(self) -> AnalyzerInfo | None:
        """Delegate to primary, fall back to secondary."""
        for backend in (self._primary, self._fallback):
            try:
                result = await backend.get_active_analyzer()
                if result is not None:
                    return result
            except Exception:
                logger.debug(
                    "get_active_analyzer failed for %s",
                    type(backend).__name__,
                    exc_info=True,
                )
        return None

    async def set_active_analyzer(self, analyzer_id: str | None) -> bool:
        """Delegate to primary, fall back to secondary."""
        for backend in (self._primary, self._fallback):
            try:
                if await backend.set_active_analyzer(analyzer_id):
                    return True
            except Exception:
                logger.debug(
                    "set_active_analyzer failed for %s",
                    type(backend).__name__,
                    exc_info=True,
                )
        return False
