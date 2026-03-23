# AuraCode

Terminal-native, vendor-agnostic AI coding assistant.

AuraCode is a modular engine that routes coding requests through pluggable adapters and router backends. It supports multiple LLM providers via AuraRouter and can distribute work across AuraGrid compute nodes.

## Quick start

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/ -x -q
```

## Architecture

```
Adapter (CLI/IDE/MCP)
    |
    v
AuraCodeEngine
    |-- SessionManager (in-memory)
    |-- AdapterRegistry
    |-- BackendRegistry
    |
    v
BaseRouterBackend (AuraRouter, local, etc.)
```

- **Adapters** translate between external interfaces and `EngineRequest`/`EngineResponse`.
- **Router backends** select a model and execute inference.
- **The engine** orchestrates sessions, routing, and error handling.

## Project layout

```
src/auracode/
  __init__.py          # Package root, __version__
  cli.py               # Click entry-point
  models/              # Pydantic v2 frozen domain models
    request.py         # EngineRequest, EngineResponse, TokenUsage, ...
    context.py         # SessionContext, FileContext
    config.py          # AuraCodeConfig
  adapters/
    base.py            # BaseAdapter ABC
  routing/
    base.py            # BaseRouterBackend ABC, ModelInfo, RouteResult
  engine/
    core.py            # AuraCodeEngine
    session.py         # SessionManager
    registry.py        # AdapterRegistry, BackendRegistry
  util/
    logging.py         # structlog configuration
tests/
  conftest.py          # Shared fixtures, mock backends
  test_models.py       # Model tests
  test_engine.py       # Engine, session, registry tests
auracode.yaml          # Default configuration
```

## License

MIT
