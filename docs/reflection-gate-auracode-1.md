# Reflection Gate 1: Contract and Surface Audit

**Date**: 2026-03-31
**Phase**: After TG1-TG5, before Phase 3
**Verdict**: PASS

## Audit Results

### 1. Can every FMoE control be expressed without abusing raw `options`? — PASS

- `ExecutionPolicy` is a first-class field on `EngineRequest` with typed sub-models for mode, routing, sovereignty, retrieval, and latency.
- `engine/core.py` normalizes legacy `options` into typed policy via `normalize_options_to_policy()`, then injects the effective policy into route options as `_execution_policy`.
- REPL commands (`/mode`, `/sovereignty`, `/retrieval`) set policy through typed enums.
- MCP tools (`auracode_generate`, `auracode_plan`, etc.) accept typed policy arguments and build `ExecutionPolicy` directly.
- Legacy `options` remain as a compatibility escape hatch.

### 2. Do REPL and MCP expose equivalent policy levers? — PASS

| Control | REPL | MCP |
|---------|------|-----|
| Execution mode | `/mode` | `execution_mode` param on generate/plan/refactor |
| Routing preference | via `/prefs` | `routing_preference` param on generate |
| Sovereignty | `/sovereignty` | `sovereignty_enforcement` param on review_diff/security_review |
| Retrieval | `/retrieval` | `retrieval_mode` available via generate |
| Trace/metadata | `/trace` | `auracode_trace` tool |
| Capabilities | `/capabilities` | via models tool |
| Status | `/status` (shows mode/sov/ret) | via models/trace |

### 3. Are unsupported capabilities surfaced as explicit degradations? — PASS

- `EmbeddedRouterBackend._check_capability_support()` generates `DegradationNotice` for:
  - `require_grid`/`require_verified` on local-only backend
  - `speculative`/`monologue` when fabric lacks support
- `FailoverBackend` generates `DegradationNotice` when over-threshold falls back.
- `FailoverBackend._route_require_primary()` raises `RuntimeError` when grid is required but unavailable — no silent fallback.
- Engine `_extract_execution_metadata()` propagates degradation notices into `EngineResponse.execution_metadata`.
- REPL `/trace` command renders degradation details to operator.

### Backward Compatibility — PASS

- `EngineRequest` still accepts construction with only the original fields.
- `options` dict still flows through and is normalized.
- All 607 tests pass (585 baseline + 22 new).

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| G1-W1 | warning | MCP tools don't yet expose `retrieval_mode` as a parameter on all tools — only via the underlying `intent` mapping. Acceptable for now. |

## Remediation

None required. G1-W1 is a minor gap that TG8 (UX convergence) can address.
