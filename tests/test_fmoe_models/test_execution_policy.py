"""Tests for typed execution policy models (TG1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auracode.models.normalization import normalize_options_to_policy
from auracode.models.request import (
    DegradationNotice,
    EngineRequest,
    EngineResponse,
    ExecutionMetadata,
    ExecutionMode,
    ExecutionPolicy,
    RequestIntent,
    RetrievalMode,
    RetrievalPolicy,
    RoutingPreference,
    SovereigntyEnforcement,
    SovereigntyPolicy,
)

# ── Enum serialization stability ──────────────────────────────────────


class TestEnumStability:
    def test_execution_mode_values(self):
        assert ExecutionMode.STANDARD == "standard"
        assert ExecutionMode.SPECULATIVE == "speculative"
        assert ExecutionMode.MONOLOGUE == "monologue"

    def test_routing_preference_values(self):
        assert RoutingPreference.AUTO == "auto"
        assert RoutingPreference.PREFER_LOCAL == "prefer_local"
        assert RoutingPreference.REQUIRE_LOCAL == "require_local"
        assert RoutingPreference.PREFER_GRID == "prefer_grid"
        assert RoutingPreference.REQUIRE_GRID == "require_grid"
        assert RoutingPreference.REQUIRE_VERIFIED == "require_verified"

    def test_sovereignty_enforcement_values(self):
        assert SovereigntyEnforcement.NONE == "none"
        assert SovereigntyEnforcement.WARN == "warn"
        assert SovereigntyEnforcement.ENFORCE == "enforce"

    def test_retrieval_mode_values(self):
        assert RetrievalMode.DISABLED == "disabled"
        assert RetrievalMode.AUTO == "auto"
        assert RetrievalMode.REQUIRED == "required"

    def test_new_intent_values(self):
        assert RequestIntent.REFACTOR == "refactor"
        assert RequestIntent.REVIEW_DIFF == "review_diff"
        assert RequestIntent.SECURITY_REVIEW == "security_review"
        assert RequestIntent.GENERATE_TESTS == "generate_tests"
        assert RequestIntent.CROSS_FILE_EDIT == "cross_file_edit"
        assert RequestIntent.ARCHITECTURE_TRACE == "architecture_trace"

    def test_enum_roundtrip(self):
        for mode in ExecutionMode:
            assert ExecutionMode(mode.value) is mode
        for pref in RoutingPreference:
            assert RoutingPreference(pref.value) is pref


# ── Policy model defaults ────────────────────────────────────────────


class TestPolicyDefaults:
    def test_execution_policy_defaults(self):
        p = ExecutionPolicy()
        assert p.mode == ExecutionMode.STANDARD
        assert p.routing == RoutingPreference.AUTO
        assert p.sovereignty.enforcement == SovereigntyEnforcement.NONE
        assert p.sovereignty.allow_cloud is True
        assert p.retrieval.mode == RetrievalMode.DISABLED
        assert p.latency.max_seconds is None

    def test_sovereignty_policy_defaults(self):
        s = SovereigntyPolicy()
        assert s.enforcement == SovereigntyEnforcement.NONE
        assert s.sensitivity_label is None
        assert s.audit_labels == []
        assert s.allow_cloud is True

    def test_retrieval_policy_defaults(self):
        r = RetrievalPolicy()
        assert r.mode == RetrievalMode.DISABLED
        assert r.require_citations is False
        assert r.anchor_preferences == []


# ── Frozen immutability ──────────────────────────────────────────────


class TestFrozenModels:
    def test_execution_policy_immutable(self):
        p = ExecutionPolicy()
        with pytest.raises(ValidationError):
            p.mode = ExecutionMode.SPECULATIVE

    def test_degradation_notice_immutable(self):
        d = DegradationNotice(capability="mode", requested="speculative", actual="standard")
        with pytest.raises(ValidationError):
            d.reason = "changed"


# ── EngineRequest backward compatibility ─────────────────────────────


class TestEngineRequestCompat:
    def test_legacy_construction(self):
        req = EngineRequest(
            request_id="1",
            intent=RequestIntent.GENERATE_CODE,
            prompt="hello",
            adapter_name="test",
        )
        assert req.execution_policy.mode == ExecutionMode.STANDARD
        assert req.options == {}

    def test_with_policy(self):
        policy = ExecutionPolicy(mode=ExecutionMode.SPECULATIVE)
        req = EngineRequest(
            request_id="2",
            intent=RequestIntent.PLAN,
            prompt="plan",
            adapter_name="test",
            execution_policy=policy,
        )
        assert req.execution_policy.mode == ExecutionMode.SPECULATIVE

    def test_with_both_options_and_policy(self):
        req = EngineRequest(
            request_id="3",
            intent=RequestIntent.CHAT,
            prompt="chat",
            adapter_name="test",
            options={"key": "value"},
            execution_policy=ExecutionPolicy(mode=ExecutionMode.MONOLOGUE),
        )
        assert req.options["key"] == "value"
        assert req.execution_policy.mode == ExecutionMode.MONOLOGUE


# ── EngineResponse with execution metadata ───────────────────────────


class TestEngineResponseMetadata:
    def test_response_without_metadata(self):
        resp = EngineResponse(request_id="1", content="hello")
        assert resp.execution_metadata is None

    def test_response_with_metadata(self):
        meta = ExecutionMetadata(
            analyzer_used="test-analyzer",
            execution_mode_used=ExecutionMode.STANDARD,
            degradations=[
                DegradationNotice(
                    capability="routing",
                    requested="require_grid",
                    actual="prefer_local",
                    reason="grid unavailable",
                )
            ],
        )
        resp = EngineResponse(
            request_id="2",
            content="output",
            execution_metadata=meta,
        )
        assert resp.execution_metadata.analyzer_used == "test-analyzer"
        assert len(resp.execution_metadata.degradations) == 1


# ── Normalization ────────────────────────────────────────────────────


class TestNormalization:
    def test_empty_options(self):
        policy, ignored = normalize_options_to_policy(None)
        assert policy == ExecutionPolicy()
        assert ignored == []

    def test_valid_options(self):
        options = {
            "execution_mode": "speculative",
            "routing_preference": "require_local",
            "retrieval_mode": "required",
            "max_seconds": "10.5",
        }
        policy, ignored = normalize_options_to_policy(options)
        assert policy.mode == ExecutionMode.SPECULATIVE
        assert policy.routing == RoutingPreference.REQUIRE_LOCAL
        assert policy.retrieval.mode == RetrievalMode.REQUIRED
        assert policy.latency.max_seconds == 10.5
        assert ignored == []

    def test_unknown_keys_ignored(self):
        options = {"execution_mode": "standard", "unknown_key": "value"}
        policy, ignored = normalize_options_to_policy(options)
        assert "unknown_key" in ignored
        assert policy.mode == ExecutionMode.STANDARD

    def test_invalid_enum_values(self):
        options = {"execution_mode": "invalid_mode"}
        policy, ignored = normalize_options_to_policy(options)
        assert "execution_mode" in ignored
        assert policy.mode == ExecutionMode.STANDARD  # default preserved

    def test_base_policy_preserved(self):
        base = ExecutionPolicy(mode=ExecutionMode.MONOLOGUE)
        options = {"routing_preference": "prefer_grid"}
        policy, ignored = normalize_options_to_policy(options, base=base)
        assert policy.mode == ExecutionMode.MONOLOGUE  # from base
        assert policy.routing == RoutingPreference.PREFER_GRID  # from options

    def test_sovereignty_options(self):
        options = {
            "sovereignty_enforcement": "enforce",
            "sensitivity_label": "SECRET",
            "allow_cloud": False,
        }
        policy, ignored = normalize_options_to_policy(options)
        assert policy.sovereignty.enforcement == SovereigntyEnforcement.ENFORCE
        assert policy.sovereignty.sensitivity_label == "SECRET"
        assert policy.sovereignty.allow_cloud is False
