# AuraCode — Developer Reference

Terminal-native, vendor-agnostic AI coding assistant built under AuraCore Dynamics Inc. AuraCode routes coding requests through a Federated Mixture-of-Experts (FMoE) fabric, selecting the right model for every task automatically.

## Architecture

AuraCode follows a layered, dependency-inverted design with strict separation between presentation (adapters), orchestration (engine), and inference (routing backends).

```
Adapters (CLI, IDE, MCP, API shim)
         |
    EngineRequest / EngineResponse
         |
    AuraCodeEngine
         |-- SessionManager (in-memory conversation state)
         |-- AdapterRegistry (adapter discovery and lookup)
         |-- BackendRegistry (routing backend management)
         |-- PreferencesManager (persistent user preferences)
         |
    BaseRouterBackend
         |-- EmbeddedRouterBackend (AuraRouter — local FMoE)
         |-- GridDelegateBackend (AuraGrid — distributed gRPC)
         |-- FailoverBackend (Grid -> Local automatic fallback)
```

### Key Design Decisions

- **Adapter pattern over plugin system.** Adapters are discovered via `importlib` package scanning. No entry points, no plugin registry. The adapter set is known at build time — we're cloning specific tools, not building a marketplace.
- **AuraRouter as library dependency, not fork.** AuraCode imports AuraRouter classes directly. `BaseRouterBackend` provides the abstraction boundary. If AuraRouter's API changes, only `EmbeddedRouterBackend` needs updating.
- **OpenAI-compatible API as universal shim.** One endpoint covers most IDE extensions. No need for per-extension protocol implementations.
- **Failover as backend wrapper, not engine logic.** `FailoverBackend` composes grid + local backends. The engine always talks to one backend — composition happens outside.
- **Async-first engine.** All engine and routing operations are `async`. Synchronous AuraRouter calls are wrapped with `asyncio.to_thread()`.
- **Frozen domain models.** All Pydantic models use `ConfigDict(frozen=True)` for immutability. Exception: `AuraCodeConfig` is mutable for runtime overrides.

## Project Structure

```
src/auracode/
  __init__.py              # Package root, __version__, public API re-exports
  app.py                   # Application bootstrap (load_config, create_application)
  cli.py                   # Unified Click CLI (repl [default], status, models, serve)
  mcp_server.py            # Reverse-MCP server factory
  models/
    request.py             # EngineRequest, EngineResponse, RequestIntent, TokenUsage, FileArtifact
    context.py             # SessionContext, FileContext
    config.py              # AuraCodeConfig
    preferences.py         # UserPreferences (persistent prefs model)
  adapters/
    base.py                # BaseAdapter ABC
    loader.py              # discover_adapters() — package scanning
    opencode/              # OpenCode adapter — AuraCode-native (default)
      adapter.py           # OpenCodeAdapter
      formatter.py         # Clean markdown response formatting
    claude_code/           # Claude Code CLI adapter
      adapter.py           # ClaudeCodeAdapter
      cli.py               # Click group: chat, do, explain, review
      formatter.py         # Rich terminal output formatting
    openai_shim/           # OpenAI API adapter (no CLI — API-only)
      adapter.py           # OpenAIShimAdapter
    copilot/               # GitHub Copilot CLI adapter (suggest, explain, commit)
      adapter.py           # CopilotAdapter
      cli.py               # Click group: suggest, explain, commit
      formatter.py         # Inline suggestion output formatting
    aider/                 # Aider file-diffing adapter (code, ask, architect)
      adapter.py           # AiderAdapter
      cli.py               # Click group: code, ask, architect
      formatter.py         # Diff-style output formatting
    codestral/             # Codestral code-completion adapter (complete, fill, chat)
      adapter.py           # CodestralAdapter
      cli.py               # Click group: complete, fill, chat
      formatter.py         # FIM completion output formatting
  repl/
    console.py             # AuraCodeConsole — interactive REPL loop
    commands.py            # Slash-command registry and built-in handlers
  routing/
    base.py                # BaseRouterBackend ABC, ModelInfo, ServiceInfo, AnalyzerInfo, RouteResult
    embedded.py            # EmbeddedRouterBackend (wraps AuraRouter ComputeFabric)
    intent_map.py          # INTENT_ROLE_MAP, map_intent_to_role(), build_context_prompt()
    mcp_catalog.py         # McpCatalogClient, ToolInfo
  engine/
    core.py                # AuraCodeEngine (execute, get_session, close_session)
    session.py             # SessionManager (in-memory dict, UUID generation)
    registry.py            # AdapterRegistry, BackendRegistry
    preferences.py         # PreferencesManager (load/save YAML prefs)
  shim/
    server.py              # create_app(), start_server(), start_server_daemon()
    openai_compat.py       # chat_completions(), completions() handlers
    models_endpoint.py     # list_models() handler
    middleware.py           # error_middleware, logging_middleware, CORS
  grid/
    client.py              # GridDelegateBackend (gRPC with mTLS, fully implemented)
    failover.py            # FailoverBackend (primary -> fallback)
    serializer.py          # engine_request_to_grid(), grid_response_to_route_result()
    messages.py            # Pure Python dataclasses mirroring proto messages
    proto/
      auracode_grid.proto  # Protobuf service definition (Execute, ExecuteStream, HealthCheck, ListModels)
  util/
    logging.py             # configure_logging() via structlog
```

## Conventions

- **Python 3.12+**, src-layout (`[tool.setuptools.packages.find] where = ["src"]`).
- All domain models use `model_config = ConfigDict(frozen=True)`.
- `AuraCodeConfig` is intentionally mutable for runtime overrides.
- ABCs use `@abstractmethod`; no default implementations.
- `async def` throughout the engine and routing layers.
- structlog for structured logging.
- Adapters are subpackages under `adapters/` with a `register(registry)` entry point. All 5 adapters (opencode, claude-code, copilot, aider, codestral) plus the openai_shim are fully implemented and wired to the engine.
- Optional dependencies are grouped: `[api]` for aiohttp, `[grid]` for gRPC, `[all]` for everything.
- Graceful degradation: missing optional packages produce helpful errors, not crashes.

## Configuration

Config lookup chain: `--config` flag > `./auracode.yaml` > `~/.auracode.yaml` > defaults.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `router_config_path` | `str \| null` | `null` | Path to AuraRouter's `auraconfig.yaml` |
| `default_adapter` | `str` | `"opencode"` | Adapter used when none specified |
| `log_level` | `str` | `"INFO"` | Logging verbosity |
| `grid_endpoint` | `str \| null` | `null` | AuraGrid gRPC endpoint |
| `grid_failover_to_local` | `bool` | `true` | Fall back to local if grid unavailable |
| `local_context_limit` | `int` | `100000` | Token threshold for grid delegation |
| `adapters` | `dict` | `{}` | Per-adapter configuration blocks |

## Intent-to-Role Mapping

The routing layer maps each `RequestIntent` to an AuraRouter role:

| Intent | Role | Rationale |
|--------|------|-----------|
| `GENERATE_CODE` | `coder` | Bounded task, speed-optimized |
| `EDIT_CODE` | `coder` | Pattern recognition, targeted modification |
| `COMPLETE_CODE` | `coder` | Lowest latency, inline completion |
| `EXPLAIN_CODE` | `reasoning` | Requires contextual understanding |
| `REVIEW` | `reasoning` | Requires judgment and architectural context |
| `CHAT` | `reasoning` | Open-ended, benefits from depth |
| `PLAN` | `reasoning` | Decomposition, frontier capability required |

### Adapter-Specific Intent Mappings

Each adapter maps its native commands to `RequestIntent` values:

| Adapter | Command | Maps to Intent |
|---------|---------|---------------|
| **opencode** | (default) | `GENERATE_CODE` |
| **claude-code** | `do` | `GENERATE_CODE` |
| **claude-code** | `explain` | `EXPLAIN_CODE` |
| **claude-code** | `review` | `REVIEW` |
| **claude-code** | `chat` | `CHAT` |
| **copilot** | `suggest` | `GENERATE_CODE` |
| **copilot** | `explain` | `EXPLAIN_CODE` |
| **copilot** | `commit` | `GENERATE_CODE` |
| **aider** | `code` | `EDIT_CODE` |
| **aider** | `ask` | `CHAT` |
| **aider** | `architect` | `PLAN` |
| **codestral** | `complete` | `COMPLETE_CODE` |
| **codestral** | `fill` | `GENERATE_CODE` |
| **codestral** | `chat` | `CHAT` |

Roles are defined in AuraRouter's `auraconfig.yaml` as ordered model chains. The `"coder"` role might chain `[local-codellama, sonnet, opus]`. The `"reasoning"` role might chain `[opus, deepseek-r1, local-phi3]`. AuraRouter tries each in order until one succeeds.

## Application Bootstrap

`create_application(config_path)` in `app.py` wires the full stack:

1. Load config (YAML file or defaults)
2. Configure structured logging
3. Create `EmbeddedRouterBackend` if AuraRouter is installed
4. If `grid_endpoint` is set: create `GridDelegateBackend` + `FailoverBackend`
5. Fall back to `StubBackend` if no real backend is available
6. Discover and register all adapters
7. Create and return `(AuraCodeEngine, AdapterRegistry, BackendRegistry, PreferencesManager)`

The bootstrap handles every combination of available/missing dependencies gracefully.

## CLI Commands

| Command | Description |
|---------|-------------|
| `auracode` | Launch the interactive REPL (default command) |
| `auracode repl` | Launch the interactive REPL (explicit) |
| `auracode status` | Show health: adapters, router status, model count |
| `auracode models` | List available models with provider and tags |
| `auracode serve [--port 8741] [--host 127.0.0.1]` | Start OpenAI-compatible API server |
| `auracode claude chat [-c FILE] [-m MODEL] [--json]` | Interactive conversation via Claude Code adapter |
| `auracode claude do PROMPT [-c FILE] [-m MODEL] [--json]` | One-shot generation |
| `auracode claude explain FILE [-c FILE] [-m MODEL] [--json]` | Explain a file |
| `auracode claude review FILE [-c FILE] [-m MODEL] [--json]` | Review code |
| `auracode copilot suggest PROMPT [-c FILE] [-m MODEL]` | Inline code suggestion |
| `auracode copilot explain PROMPT [-c FILE] [-m MODEL]` | Explain code |
| `auracode copilot commit PROMPT [-c FILE] [-m MODEL]` | Generate commit message |
| `auracode aider code PROMPT [-c FILE] [-r FILE] [-m MODEL]` | Edit code with diffs |
| `auracode aider ask PROMPT [-c FILE] [-m MODEL]` | Ask about code |
| `auracode aider architect PROMPT [-c FILE] [-m MODEL]` | Plan architecture |
| `auracode codestral complete PROMPT [--prefix P] [--suffix S] [-c FILE] [-m MODEL]` | Code completion (FIM) |
| `auracode codestral fill PROMPT [--prefix P] [--suffix S] [-c FILE] [-m MODEL]` | Fill-in-the-middle |
| `auracode codestral chat PROMPT [-c FILE] [-m MODEL]` | Chat about code |
| `auracode --version` | Show version |

## API Shim Endpoints

When running `auracode serve`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | OpenAI chat completions (streaming + non-streaming) |
| `/v1/completions` | POST | Legacy OpenAI completions |
| `/v1/models` | GET | List models (OpenAI format) |
| `/health` | GET | Liveness check |

Server binds to `127.0.0.1` by default (no external exposure). Port 8741.

## MCP Tools

The reverse-MCP server (`mcp_server.py`) exposes:

| Tool | Signature | Description |
|------|-----------|-------------|
| `auracode_generate` | `(prompt, intent?, context_dir?)` | Generate code |
| `auracode_explain` | `(file_path)` | Explain file contents |
| `auracode_review` | `(file_path)` | Review code |
| `auracode_models` | `()` | List available models |

## REPL Slash Commands

The interactive REPL (`auracode` or `auracode repl`) supports the following slash commands:

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `/?` | Show available commands and usage hints |
| `/status` | | Show engine health, active adapter/analyzer, catalog counts |
| `/catalog` | `/models` | List models, services, and analyzers |
| `/analyzer` | | View or switch the active route analyzer |
| `/adapter` | | Switch or list adapters |
| `/claude` | | Switch to Claude Code adapter |
| `/copilot` | | Switch to Copilot adapter |
| `/aider` | | Switch to Aider adapter |
| `/codestral` | | Switch to Codestral adapter |
| `/context` | `/ctx` | Add or list context files |
| `/clear` | | Clear session history and/or context |
| `/prefs` | `/preferences` | View or set persistent preferences |
| `/explain` | | Explain a file |
| `/review` | | Review a file |
| `/quit` | `/q`, `/exit` | Exit AuraCode |

## Catalog Methods on BaseRouterBackend

`BaseRouterBackend` provides optional catalog methods with default implementations (return empty/False). `EmbeddedRouterBackend` overrides these when AuraRouter is available.

| Method | Return Type | Description |
|--------|-------------|-------------|
| `list_services()` | `list[ServiceInfo]` | MCP services in the catalog |
| `list_analyzers()` | `list[AnalyzerInfo]` | Route analyzers available |
| `get_active_analyzer()` | `AnalyzerInfo \| None` | Currently active route analyzer |
| `set_active_analyzer(analyzer_id)` | `bool` | Set the active analyzer; returns True on success |
| `catalog_summary()` | `dict[str, int]` | Counts of models, services, analyzers |

Key data models:
- `ServiceInfo`: `service_id`, `display_name`, `description`, `provider`, `endpoint`, `tools` (list[str]), `status`
- `AnalyzerInfo`: `analyzer_id`, `display_name`, `description`, `kind`, `provider`, `capabilities` (list[str]), `is_active`

## User Preferences

Persistent preferences stored in `~/.auracode/preferences.yaml`, managed by `PreferencesManager`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_adapter` | `str` | `"opencode"` | Adapter to use on startup |
| `show_model_in_response` | `bool` | `True` | Display model name in responses |
| `show_token_usage` | `bool` | `False` | Show token counts |
| `history_limit` | `int` | `100` | Max messages in session history |
| `markdown_rendering` | `bool` | `True` | Render markdown in REPL |
| `prefer_local` | `bool` | `False` | Prefer local models over cloud |
| `active_analyzer` | `str \| None` | `None` | Active route analyzer ID |

`PreferencesManager` methods: `load()`, `save()`, `get(key)`, `set(key, value)`. Setting a preference auto-saves to disk. Type coercion is handled automatically (e.g., string "true" to bool).

## Relationship to AuraCore Ecosystem

AuraCode sits atop three AuraCore systems:

- **AuraRouter** (open source, Apache-2.0) — Multi-model MCP routing fabric. AuraCode embeds it as the `EmbeddedRouterBackend`. Handles model selection, fallback chains, cost optimization, and intent analysis. Models: Ollama, llama.cpp, Claude, Gemini, OpenAI-compatible.
- **AuraGrid** (proprietary) — Federated compute fabric. AuraCode delegates heavy requests via gRPC (`GridDelegateBackend`). Auction-based resource allocation, event-sourced durability, split-brain resilient, mTLS-secured. Provides distributed inference for requests that exceed local capacity.
- **AuraXLM** (proprietary) — Decentralized mixture-of-experts with RAG. When connected via AuraRouter, provides retrieval-augmented generation grounded in your codebase, domain-specific fine-tuned models via Model Foundry, and geospatial intelligence capabilities.

AuraCode works standalone — it does not require AuraGrid or AuraXLM. But each layer adds capabilities: AuraRouter adds intelligent routing, AuraGrid adds distributed scale, AuraXLM adds domain-specific knowledge.

## Testing

```bash
# Full suite (360+ tests)
pytest tests/ -x -q

# By component
pytest tests/test_models.py -x -q          # Domain models
pytest tests/test_engine.py -x -q          # Engine, session, registry
pytest tests/test_preferences.py -x -q     # UserPreferences, PreferencesManager
pytest tests/test_adapters/ -x -q          # Adapter discovery, Claude Code, OpenCode
pytest tests/test_repl/ -x -q              # REPL console, slash commands
pytest tests/test_routing/ -x -q           # Embedded router, intent map, MCP catalog
pytest tests/test_shim/ -x -q              # API shim server
pytest tests/test_grid/ -x -q              # Grid client, failover
pytest tests/test_integration/ -x -q       # End-to-end bootstrap, CLI, full path
```

All routing and grid tests are fully mocked — they pass without AuraRouter or AuraGrid installed.

## Dependencies

| Group | Packages |
|-------|----------|
| Core | `pydantic>=2.0`, `click>=8.0`, `structlog`, `PyYAML>=6.0`, `rich>=13.0` |
| `[api]` | `aiohttp>=3.9` |
| `[grid]` | `grpcio>=1.60`, `grpcio-tools>=1.60`, `protobuf>=4.25` |
| `[dev]` | `pytest>=8.0`, `pytest-asyncio`, `pytest-aiohttp`, `ruff`, plus `[all]` |
