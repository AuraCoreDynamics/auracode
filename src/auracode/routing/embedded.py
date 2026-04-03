"""Embedded AuraRouter backend for AuraCode."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import structlog

from auracode.models.context import SessionContext
from auracode.models.request import (
    DegradationNotice,
    ExecutionMode,
    RequestIntent,
    RoutingPreference,
)
from auracode.routing.artifacts import execute_modifications, parse_artifact_payload
from auracode.routing.base import (
    AnalyzerInfo,
    BackendCapability,
    BaseRouterBackend,
    ModelInfo,
    RouteResult,
    ServiceInfo,
)
from auracode.routing.intent_map import (
    build_context_prompt,
    build_file_constraints,
    map_intent_to_capabilities,
    map_intent_to_role,
)

log = structlog.get_logger()

ACTIONABLE_INTENTS = {
    RequestIntent.EDIT_CODE,
    RequestIntent.GENERATE_CODE,
    RequestIntent.REFACTOR,
    RequestIntent.CROSS_FILE_EDIT,
}


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
        self._last_route_options: dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Routing hints
    # ------------------------------------------------------------------ #

    def _extract_languages(self, context: SessionContext | None) -> list[str]:
        """Extract unique programming languages from session files."""
        if context is None:
            return []
        seen: set[str] = set()
        for f in context.files:
            if f.language and f.language not in seen:
                seen.add(f.language)
        return sorted(seen)  # deterministic ordering

    def _build_route_options(
        self,
        intent: RequestIntent,
        context: SessionContext | None,
        caller_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build the routing options payload.

        Serializes typed execution policy, intent semantics, capability
        requests, and context hints into a stable backend payload.
        Caller-provided options take precedence on key collision.
        """
        opts: dict[str, Any] = {
            "intent": intent.value,
            "routing_hints": self._extract_languages(context),
            "file_constraints": build_file_constraints(context),
            "requested_capabilities": map_intent_to_capabilities(intent),
        }

        # Inject typed policy if present in caller options (set by engine).
        if caller_options and "_execution_policy" in caller_options:
            opts["execution_policy"] = caller_options["_execution_policy"]

        if caller_options:
            opts.update(caller_options)
        return opts

    def _check_capability_support(
        self,
        requested_mode: ExecutionMode,
        requested_routing: RoutingPreference,
        policy_dict: dict | None = None,
    ) -> list[DegradationNotice]:
        """Check if the configured fabric supports the requested capabilities.

        Returns a list of degradation notices for unsupported features.
        """
        degradations: list[DegradationNotice] = []

        # The embedded backend always runs locally.
        if requested_routing in (
            RoutingPreference.REQUIRE_GRID,
            RoutingPreference.REQUIRE_VERIFIED,
        ):
            degradations.append(
                DegradationNotice(
                    capability="routing",
                    requested=requested_routing.value,
                    actual=RoutingPreference.PREFER_LOCAL.value,
                    reason=(
                        "Embedded backend executes locally; grid/verified routing not available."
                    ),
                )
            )

        # Check if fabric supports streaming for speculative mode.
        if requested_mode == ExecutionMode.SPECULATIVE:
            if not hasattr(self._fabric, "execute_speculative"):
                degradations.append(
                    DegradationNotice(
                        capability="execution_mode",
                        requested="speculative",
                        actual="standard",
                        reason="Fabric does not support speculative execution.",
                    )
                )

        if requested_mode == ExecutionMode.MONOLOGUE:
            if not hasattr(self._fabric, "execute_monologue"):
                degradations.append(
                    DegradationNotice(
                        capability="execution_mode",
                        requested="monologue",
                        actual="standard",
                        reason="Fabric does not support monologue execution.",
                    )
                )

        # Sovereignty enforcement: if enforce + no cloud allowed, flag if
        # the fabric uses cloud providers.
        if policy_dict:
            sov = policy_dict.get("sovereignty", {})
            enforcement = sov.get("enforcement", "none")
            allow_cloud = sov.get("allow_cloud", True)
            if enforcement == "enforce" and not allow_cloud:
                # Embedded backend is local — this is satisfied.
                pass  # Local execution complies with no-cloud policy.

            # Retrieval enforcement
            ret = policy_dict.get("retrieval", {})
            ret_mode = ret.get("mode", "disabled")
            if ret_mode == "required":
                # Embedded backend doesn't have native RAG — degrade.
                degradations.append(
                    DegradationNotice(
                        capability="retrieval",
                        requested="required",
                        actual="disabled",
                        reason="Embedded backend does not support retrieval augmentation.",
                    )
                )

        return degradations

    @staticmethod
    def _routing_hints_prefix(route_options: dict[str, Any]) -> str:
        """Format route options as a structured prefix block for the prompt."""
        hints = route_options.get("routing_hints", [])
        intent_val = route_options.get("intent", "")
        if not hints and not intent_val:
            return ""
        import json

        block = json.dumps(
            {"intent": intent_val, "routing_hints": hints},
            separators=(",", ":"),
        )
        return f"[ROUTE_OPTIONS]{block}[/ROUTE_OPTIONS]\n"

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

        route_options = self._build_route_options(intent, context, options)
        self._last_route_options = route_options

        # Capability negotiation: check requested mode/routing against fabric.
        policy_dict = (
            route_options.get("execution_policy") or route_options.get("_execution_policy") or {}
        )
        requested_mode = (
            ExecutionMode(policy_dict.get("mode", "standard"))
            if policy_dict
            else ExecutionMode.STANDARD
        )
        requested_routing = (
            RoutingPreference(policy_dict.get("routing", "auto"))
            if policy_dict
            else RoutingPreference.AUTO
        )
        degradations = self._check_capability_support(
            requested_mode, requested_routing, policy_dict
        )

        if degradations:
            log.info(
                "embedded.capability_degradation",
                degradations=[d.model_dump() for d in degradations],
            )

        context_prefix = build_context_prompt(context)
        hints_prefix = self._routing_hints_prefix(route_options)
        full_prompt = hints_prefix + context_prefix + prompt

        fabric_result = await asyncio.to_thread(
            self._fabric.execute,
            role,
            full_prompt,
            options=route_options,
        )

        if fabric_result is None:
            raise RuntimeError(f"All models failed for role '{role}' — no response from fabric.")

        # fabric.execute() returns GenerateResult or str — normalise to str
        result_text = fabric_result.text if hasattr(fabric_result, "text") else str(fabric_result)
        model_used = (
            fabric_result.model_id
            if hasattr(fabric_result, "model_id") and fabric_result.model_id
            else (self._config_loader.get_role_chain(role) or ["unknown"])[0]
        )

        route_result = RouteResult(
            content=result_text,
            model_used=model_used,
            metadata={"analyzer_used": self._get_active_analyzer_id()},
            degradations=degradations,
        )

        # --- Artifact execution for actionable intents ----------------
        if intent in ACTIONABLE_INTENTS and route_result:
            payload = parse_artifact_payload(route_result.content)
            if payload and payload.modifications:
                working_dir = context.working_directory if context else "."
                results = execute_modifications(payload, working_dir)

                upstream_trace = route_result.metadata.get("execution_trace", [])
                executor_trace: list[str] = []
                for r in results:
                    if r.success:
                        executor_trace.append(
                            f"Executor: {r.file_path} {r.modification_type} applied"
                        )
                    else:
                        executor_trace.append(f"Executor: {r.file_path} FAILED — {r.error}")
                any_failed = any(not r.success for r in results)
                if any_failed:
                    executor_trace.append("Executor: ROLLBACK — all files restored")
                full_trace = upstream_trace + executor_trace

                route_result = RouteResult(
                    content=route_result.content,
                    model_used=route_result.model_used,
                    usage=route_result.usage,
                    metadata={
                        **route_result.metadata,
                        "artifact_execution": [
                            {"file": r.file_path, "ok": r.success, "error": r.error}
                            for r in results
                        ],
                        "execution_trace": full_trace,
                    },
                    degradations=route_result.degradations,
                )

        return route_result

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

    def _get_active_analyzer_id(self) -> str | None:
        """Return the active analyzer ID from the config loader, or None."""
        try:
            return self._config_loader.get_active_analyzer()
        except Exception:
            return None

    async def get_capabilities(self) -> list[BackendCapability]:
        """Return capabilities supported by the embedded fabric."""
        caps = [
            BackendCapability(capability_id="code_generation", supported=True),
            BackendCapability(capability_id="reasoning", supported=True),
            BackendCapability(
                capability_id="streaming", supported=hasattr(self._fabric, "execute_stream")
            ),
            BackendCapability(
                capability_id="speculative", supported=hasattr(self._fabric, "execute_speculative")
            ),
            BackendCapability(
                capability_id="monologue", supported=hasattr(self._fabric, "execute_monologue")
            ),
            BackendCapability(capability_id="local_execution", supported=True),
            BackendCapability(capability_id="grid_execution", supported=False),
        ]
        return caps

    # ------------------------------------------------------------------ #
    # Streaming
    # ------------------------------------------------------------------ #

    async def route_stream(
        self,
        prompt: str,
        intent: RequestIntent,
        context: SessionContext | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream response tokens from the fabric.

        Tries ``execute_stream`` first (generator-based streaming).  If the
        fabric does not support streaming yet, falls back to ``execute`` and
        yields the complete response as a single chunk.
        """
        role = map_intent_to_role(intent)
        context_prefix = build_context_prompt(context)
        full_prompt = context_prefix + prompt

        # Attempt true streaming via execute_stream.
        if hasattr(self._fabric, "execute_stream"):
            try:
                stream = self._fabric.execute_stream(role, full_prompt)
                # execute_stream may be sync iterator — run chunks in thread.
                sentinel = object()
                it = iter(stream)
                while True:
                    chunk = await asyncio.to_thread(next, it, sentinel)
                    if chunk is sentinel:
                        break
                    yield chunk
                return
            except Exception:
                log.debug(
                    "embedded.stream_fallback", reason="execute_stream failed, using execute()"
                )

        # Fallback: non-streaming execute.
        fabric_result = await asyncio.to_thread(self._fabric.execute, role, full_prompt)
        if fabric_result is None:
            raise RuntimeError(f"All models failed for role '{role}' — no response from fabric.")
        yield fabric_result.text if hasattr(fabric_result, "text") else str(fabric_result)

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
