"""Normalize legacy options into typed execution policy."""

from __future__ import annotations

import structlog

from auracode.models.request import (
    ExecutionMode,
    ExecutionPolicy,
    LatencyBudget,
    RetrievalMode,
    RetrievalPolicy,
    RoutingPreference,
    SovereigntyEnforcement,
    SovereigntyPolicy,
)

log = structlog.get_logger()

# Keys in the legacy options bag that map to typed policy fields.
_KNOWN_OPTION_KEYS = {
    "execution_mode",
    "routing_preference",
    "sovereignty_enforcement",
    "sensitivity_label",
    "allow_cloud",
    "retrieval_mode",
    "require_citations",
    "max_seconds",
    "prefer_fast",
}


def normalize_options_to_policy(
    options: dict[str, object] | None,
    base: ExecutionPolicy | None = None,
) -> tuple[ExecutionPolicy, list[str]]:
    """Convert legacy options dict into an ExecutionPolicy.

    Returns (policy, ignored_keys) where ignored_keys lists option keys
    that were present but not mapped.
    """
    if base is None:
        base = ExecutionPolicy()
    if not options:
        return base, []

    ignored: list[str] = []
    mode = base.mode
    routing = base.routing
    sov = base.sovereignty
    ret = base.retrieval
    lat = base.latency

    for key, value in options.items():
        if key == "execution_mode":
            try:
                mode = ExecutionMode(str(value))
            except ValueError:
                ignored.append(key)
        elif key == "routing_preference":
            try:
                routing = RoutingPreference(str(value))
            except ValueError:
                ignored.append(key)
        elif key == "sovereignty_enforcement":
            try:
                sov = SovereigntyPolicy(
                    enforcement=SovereigntyEnforcement(str(value)),
                    sensitivity_label=sov.sensitivity_label,
                    audit_labels=sov.audit_labels,
                    allow_cloud=sov.allow_cloud,
                )
            except ValueError:
                ignored.append(key)
        elif key == "sensitivity_label":
            sov = SovereigntyPolicy(
                enforcement=sov.enforcement,
                sensitivity_label=str(value) if value else None,
                audit_labels=sov.audit_labels,
                allow_cloud=sov.allow_cloud,
            )
        elif key == "allow_cloud":
            sov = SovereigntyPolicy(
                enforcement=sov.enforcement,
                sensitivity_label=sov.sensitivity_label,
                audit_labels=sov.audit_labels,
                allow_cloud=bool(value),
            )
        elif key == "retrieval_mode":
            try:
                ret = RetrievalPolicy(
                    mode=RetrievalMode(str(value)),
                    require_citations=ret.require_citations,
                    anchor_preferences=ret.anchor_preferences,
                )
            except ValueError:
                ignored.append(key)
        elif key == "require_citations":
            ret = RetrievalPolicy(
                mode=ret.mode,
                require_citations=bool(value),
                anchor_preferences=ret.anchor_preferences,
            )
        elif key == "max_seconds":
            try:
                lat = LatencyBudget(max_seconds=float(str(value)), prefer_fast=lat.prefer_fast)
            except (ValueError, TypeError):
                ignored.append(key)
        elif key == "prefer_fast":
            lat = LatencyBudget(max_seconds=lat.max_seconds, prefer_fast=bool(value))
        elif key not in _KNOWN_OPTION_KEYS:
            ignored.append(key)

    if ignored:
        log.debug("normalization.ignored_options", keys=ignored)

    policy = ExecutionPolicy(
        mode=mode,
        routing=routing,
        sovereignty=sov,
        retrieval=ret,
        latency=lat,
    )
    return policy, ignored
