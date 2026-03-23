"""Failover backend that tries a primary backend then falls back."""

from __future__ import annotations

import logging
from typing import Any

from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult

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
        estimated = self._estimate_tokens(prompt, context)

        # If over threshold, go directly to fallback.
        if estimated > self._threshold:
            logger.info(
                "Estimated tokens (%d) exceed threshold (%d); using fallback.",
                estimated,
                self._threshold,
            )
            return await self._fallback.route(prompt, intent, context, options)

        # Check if primary is healthy before attempting.
        primary_healthy = False
        try:
            primary_healthy = await self._primary.health_check()
        except Exception:
            logger.debug("Primary health check raised", exc_info=True)

        if not primary_healthy:
            logger.info("Primary unhealthy; routing to fallback.")
            return await self._fallback.route(prompt, intent, context, options)

        # Try primary, fall back on error.
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
                logger.debug(
                    "list_models failed for %s", type(backend).__name__, exc_info=True
                )

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
