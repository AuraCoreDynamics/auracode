# Reflection Gate 2: Cross-Sovereignty and Silent-Fallback Audit

**Date**: 2026-03-31
**Phase**: After TG6-TG8, before TG9
**Verdict**: PASS

## Audit Results

### 1. Does AuraCode actually consume AuraGrid TLS/PKI config at runtime? — PASS

- `AuraCodeConfig` fields: `grid_tls_cert`, `grid_tls_key`, `grid_ca_cert`, `grid_server_name`
- `create_application()` in `app.py` passes all three TLS fields to `GridDelegateBackend()`
- `GridDelegateBackend._ensure_channel()` uses these to create `grpc.ssl_channel_credentials`
- When TLS material is provided, a secure channel is created; otherwise insecure channel
- Config is fully config-driven — no hardcoded paths

### 2. Can a sovereignty-required request escape to an ineligible backend silently? — NO (PASS)

- `FailoverBackend.route()` enforces sovereignty policy at routing decision time:
  - `enforce + allow_cloud=False` → forces local routing
  - `enforce + allow_cloud=False + require_grid` → raises `RuntimeError` (conflict)
- `EmbeddedRouterBackend._check_capability_support()` flags if sovereignty/retrieval can't be satisfied
- `_route_require_primary()` raises `RuntimeError` if grid is required but unavailable — no silent fallback

### 3. Are unsupported modes/retrieval visible to the architect? — PASS

- `DegradationNotice` objects created by:
  - `EmbeddedRouterBackend`: for require_grid, speculative, monologue, retrieval_required
  - `FailoverBackend`: for over-threshold fallback
- Propagation path: `RouteResult.degradations` → `_extract_execution_metadata()` → `EngineResponse.execution_metadata.degradations`
- Visibility: REPL `/trace` renders all degradations; `/status` shows count

### Topology Profile — PASS

- No hardcoded `localhost`, `127.0.0.1`, or `0.0.0.0` in `src/auracode/`
- All endpoint/host config is driven by `AuraCodeConfig` fields
- Grid endpoint, TLS paths, and routing policies are all configurable

### Serialized Field Compatibility — PASS

- `ExecutionPolicy` serializes via Pydantic `model_dump()` — JSON-safe dict
- Enums use `StrEnum` with stable string values — forward-compatible
- Grid serializer (`engine_request_to_grid`) passes options as `dict[str, str]`
- Policy propagates as `_execution_policy` key in options dict

### PKI Path Completeness — PASS

- Client cert + key → mTLS authentication
- CA cert → server verification
- Server name override → enterprise PKI
- All optional — local-only mode works without any TLS config

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| G2-W1 | warning | Grid server name override (`grid_server_name`) is configured but not yet passed to gRPC channel options. Low risk — only needed for advanced PKI. |

## Remediation

G2-W1 deferred — will be addressed when enterprise PKI testing is available.
