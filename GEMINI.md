# AuraCode — Gemini Agent Reference

This file provides Gemini with the operational context needed to work in the AuraCode project. For full architecture and design decisions see `CLAUDE.md`.

## Quick Facts

- **Language:** Python 3.12+, src-layout (`src/auracode/`)
- **Conda env:** `aurarouter`
- **Test command:** `pytest tests/ -x -q`
- **Linter/formatter:** ruff (`pyproject.toml`)

## Code Style — Critical Rules

### Line length: 100 characters (hard limit)

`line-length = 100` is set in `pyproject.toml`. ruff enforces **E501** (line too long) with no exceptions. This applies to:

- Source code
- Test files
- **Docstrings** (ruff-format does NOT reflow docstring prose — you must wrap manually)
- **Inline comments**

**Pre-commit hooks run `ruff check` then `ruff-format`.** Both must pass or the commit is rejected.

### What ruff-format fixes automatically

- Expressions that can be split (function call args, imports, list/dict literals)
- Trailing commas

### What ruff-format does NOT fix (requires manual wrapping)

- Docstring content (prose inside `"""..."""`)
- Inline `#` comments that are too long
- String literals that are inherently long

### Practical guidelines for test authors

```python
# BAD — docstring exceeds 100 chars:
def test_something(self):
    """Backwards compat: no routing context on GenerateResult → RouteResult.routing_context is None."""

# GOOD — split to multi-line:
def test_something(self):
    """Backwards compat: no routing context on GenerateResult.

    RouteResult.routing_context must be None when routing_context is absent.
    """
```

```python
# BAD — long function call argument list:
result = SomeModel(field_one="long value here", field_two="another long value", field_three=rc)

# GOOD — trailing-comma expanded form:
result = SomeModel(
    field_one="long value here",
    field_two="another long value",
    field_three=rc,
)
```

```python
# BAD — dict comprehension with long key list on one line:
orig = {k: sys.modules.get(k) for k in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]}

# GOOD — wrap the for clause:
orig = {
    k: sys.modules.get(k)
    for k in ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
}
```

## Checking Before Committing

```bash
# Run ruff check (lint)
conda run -n aurarouter ruff check src/ tests/

# Run ruff-format check (style)
conda run -n aurarouter ruff format --check src/ tests/

# Full test suite (includes test_lint.py which runs ruff as a test)
conda run -n aurarouter pytest tests/ -x -q
```

## Architecture Summary

```
Adapters (CLI, IDE, MCP, OpenAI shim)
    → AuraCodeEngine
        → BaseRouterBackend
            → EmbeddedRouterBackend (AuraRouter)
            → GridDelegateBackend (AuraGrid gRPC)
            → FailoverBackend
```

- Domain models: `src/auracode/models/` — all `frozen=True` Pydantic models
- Routing: `src/auracode/routing/` — `RouteResult` carries optional `routing_context: dict | None`
- Grid: `src/auracode/grid/` — gRPC delegation + serializer preserves `routing_context`
- Shim: `src/auracode/shim/` — OpenAI-compat API; surfaces `routing_context` as `_aura_routing_context`

## Key Invariants

- `RouteResult.routing_context` is `None` when AuraRouter does not provide routing context (backwards compat).
- `ExecutionMetadata.routing_context` mirrors what the backend returned.
- `_aura_routing_context` appears in OpenAI shim responses only when metadata is non-None and routing_context is present.
- Hard-route degradation (`DegradationNotice(capability="hard_routing")`) is emitted only for empty or very short responses from a hard-routed local model.
- All tests are fully mocked — no AuraRouter or AuraGrid installation required.
