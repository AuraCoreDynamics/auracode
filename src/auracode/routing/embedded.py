"""Embedded AuraRouter backend for AuraCode."""

from __future__ import annotations

import asyncio
from typing import Any

from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.base import (
    AnalyzerInfo,
    BaseRouterBackend,
    ModelInfo,
    RouteResult,
    ServiceInfo,
)
from auracode.routing.intent_map import build_context_prompt, map_intent_to_role


class EmbeddedRouterBackend(BaseRouterBackend):
    """Wraps AuraRouter's ``ComputeFabric`` as an AuraCode routing backend.

    All AuraRouter types are imported lazily so that the module can be loaded
    even when AuraRouter is not installed (tests mock the imports).
    """

    def __init__(self, config_path: str | None = None) -> None:
        from aurarouter.config import ConfigLoader
        from aurarouter.fabric import ComputeFabric

        self._config_loader = ConfigLoader(config_path=config_path)
        self._fabric = ComputeFabric(config=self._config_loader)

    # ------------------------------------------------------------------ #
    # BaseRouterBackend interface
    # ------------------------------------------------------------------ #

    async def route(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> RouteResult:
        role = map_intent_to_role(intent)

        context_prefix = build_context_prompt(context)
        full_prompt = context_prefix + prompt

        result_text: str | None = await asyncio.to_thread(self._fabric.execute, role, full_prompt)

        if result_text is None:
            raise RuntimeError(f"All models failed for role '{role}' — no response from fabric.")

        # Try to identify which model was used from the config chain.
        chain = self._config_loader.get_role_chain(role)
        model_used = chain[0] if chain else "unknown"

        return RouteResult(
            content=result_text,
            model_used=model_used,
        )

    async def list_models(self) -> list[ModelInfo]:
        model_ids = self._config_loader.get_all_model_ids()
        models: list[ModelInfo] = []
        for mid in model_ids:
            cfg = self._config_loader.get_model_config(mid)
            models.append(
                ModelInfo(
                    model_id=mid,
                    provider=cfg.get("provider", "unknown"),
                    tags=cfg.get("tags", []),
                )
            )
        return models

    async def health_check(self) -> bool:
        try:
            return (
                self._config_loader is not None
                and self._fabric is not None
                and bool(self._config_loader.config)
            )
        except Exception:
            return False

    # ------------------------------------------------------------------ #
    # Catalog methods
    # ------------------------------------------------------------------ #

    async def list_services(self) -> list[ServiceInfo]:
        """Query AuraRouter catalog for services."""
        try:
            entries = self._config_loader.catalog_list(kind="service")
            result: list[ServiceInfo] = []
            for sid in entries:
                data = self._config_loader.catalog_get(sid)
                if data:
                    result.append(
                        ServiceInfo(
                            service_id=sid,
                            display_name=data.get("display_name", sid),
                            description=data.get("description", ""),
                            provider=data.get("provider", ""),
                            endpoint=data.get("endpoint", ""),
                            tools=data.get("tools", []),
                            status=data.get("status", "registered"),
                        )
                    )
            return result
        except Exception:
            return []

    async def list_analyzers(self) -> list[AnalyzerInfo]:
        """Query AuraRouter catalog for analyzers."""
        try:
            active_id = self._config_loader.get_active_analyzer()
            entries = self._config_loader.catalog_list(kind="analyzer")
            result: list[AnalyzerInfo] = []
            for aid in entries:
                data = self._config_loader.catalog_get(aid)
                if data:
                    result.append(
                        AnalyzerInfo(
                            analyzer_id=aid,
                            display_name=data.get("display_name", aid),
                            description=data.get("description", ""),
                            kind=data.get("analyzer_kind", ""),
                            provider=data.get("provider", ""),
                            capabilities=data.get("capabilities", []),
                            is_active=(aid == active_id),
                        )
                    )
            return result
        except Exception:
            return []

    async def get_active_analyzer(self) -> AnalyzerInfo | None:
        """Get the active analyzer."""
        try:
            active_id = self._config_loader.get_active_analyzer()
            if not active_id:
                return None
            data = self._config_loader.catalog_get(active_id)
            if not data:
                return None
            return AnalyzerInfo(
                analyzer_id=active_id,
                display_name=data.get("display_name", active_id),
                description=data.get("description", ""),
                kind=data.get("analyzer_kind", ""),
                provider=data.get("provider", ""),
                capabilities=data.get("capabilities", []),
                is_active=True,
            )
        except Exception:
            return None

    async def set_active_analyzer(self, analyzer_id: str | None) -> bool:
        """Set the active analyzer in AuraRouter config."""
        try:
            self._config_loader.set_active_analyzer(analyzer_id)
            return True
        except Exception:
            return False
