# AuraCode

Terminal-native, vendor-agnostic AI coding assistant built under AuraCore Dynamics Inc.

## Architecture

AuraCode follows a layered, dependency-inverted design:

```
Adapters (CLI, IDE, MCP)  -->  Engine  -->  Router Backends (AuraRouter, local, grid)
                                  |
                            SessionManager
```

- **Models** (`src/auracode/models/`): Pydantic v2 frozen data classes. All request/response objects are immutable.
- **Adapters** (`src/auracode/adapters/`): Translate external I/O into `EngineRequest`/`EngineResponse`. Each adapter implements `BaseAdapter`.
- **Router Backends** (`src/auracode/routing/`): Select a model and execute inference. Implement `BaseRouterBackend`.
- **Engine** (`src/auracode/engine/`): `AuraCodeEngine` is the orchestrator. `SessionManager` tracks conversation state in memory. Registries manage adapters and backends.
- **CLI** (`src/auracode/cli.py`): Click-based entry-point.
- **Util** (`src/auracode/util/`): Cross-cutting concerns (logging via structlog).

## Conventions

- **Python 3.12+**, src-layout.
- All domain models use `model_config = ConfigDict(frozen=True)`.
- Config model (`AuraCodeConfig`) is intentionally mutable for runtime overrides.
- ABCs use `@abstractmethod`; no default implementations.
- Async throughout the engine and routing layers.
- structlog for structured logging.

## Testing

```bash
# Activate environment and install dev deps
pip install -e ".[dev]"

# Run tests
pytest tests/ -x -q
```

Tests live in `tests/`. Fixtures and mock backends are in `tests/conftest.py`.

## Configuration

Default config lives in `auracode.yaml` at the project root. Keys:

| Key | Default | Purpose |
|-----|---------|---------|
| `default_adapter` | `claude-code` | Adapter used when none specified |
| `log_level` | `INFO` | Logging verbosity |
| `grid_endpoint` | `null` | AuraGrid endpoint for distributed compute |
| `grid_failover_to_local` | `true` | Fall back to local if grid is unavailable |
| `local_context_limit` | `100000` | Max context tokens for local models |

## Dependencies

Runtime: pydantic>=2.0, click>=8.0, structlog, PyYAML>=6.0
Dev: pytest>=8.0, pytest-asyncio
