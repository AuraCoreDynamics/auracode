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
- **Typed execution policy over options bag.** `ExecutionPolicy` on `EngineRequest` is the source of truth for routing decisions (mode, sovereignty, retrieval, latency). Legacy `options: dict` remains as a compatibility escape hatch; the engine normalizes options into typed policy via `normalize_options_to_policy()`.
- **Explicit degradation over silent fallback.** When a requested capability cannot be satisfied (e.g., `require_grid` on a local-only backend), the system records a `DegradationNotice` and surfaces it through `ExecutionMetadata`. Silent fallback is a bug.
- **Capability-aware routing.** `EmbeddedRouterBackend` checks requested execution mode and routing preference against actual fabric capabilities and records typed degradation notices.
- **Policy precedence:** per-request `ExecutionPolicy` > REPL session state > `UserPreferences` > `AuraCodeConfig` defaults.
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
    base.py                # BaseRouterBackend ABC, ModelInfo, ServiceInfo, RouteResult
    embedded.py            # EmbeddedRouterBackend (wraps AuraRouter ComputeFabric)
    intent_map.py          # INTENT_ROLE_MAP, map_intent_to_role(), build_context_prompt()
    auraxlm_hook.py        # AuraXLM enterprise neural retrieval client & fallback hook
    mcp_catalog.py         # McpCatalogClient, ToolInfo
  engine/
    core.py                # AuraCodeEngine (execute, execute_loop, session orchestration)
    agent_loop.py          # AgenticExecutionLoop (self-healing, bounded 3-turn budget)
    repo_map.py            # RepoMapBuilder (zero-vector deterministic AST map <2KB)
    session.py             # SessionManager (in-memory dict, UUID generation)
    registry.py            # AdapterRegistry, BackendRegistry
    preferences.py         # PreferencesManager (load/save YAML prefs)
    fleet_manager.py       # FleetWorkspaceManager (multi-project workspace orchestration)
  bundle/
    manifest.py            # AppManifest and CellGovernanceSpec validation
    packager.py            # BundlePackager (.aurabundle archive packaging & inspection)
  git/
    mirror_service.py      # GitMirrorService (bare mirror management)
    grid_mirror.py         # GridMirrorOrchestrator (distributed bare mirrors on AuraGrid)
    poller.py              # GitMirrorPoller (background push poller with preflight gate)
    conflict_resolver.py   # ConflictMarkerParser and MergeConflictResolver (3-way merge)
    commit_synthesizer.py  # CommitSynthesizer (conventional commits from staged diffs)
  shim/
    server.py              # create_app(), start_server(), start_server_daemon()
    event_bus.py           # MissionEventBus (WebSocket telemetry streaming)
    ui_endpoints.py        # REST and WebSocket handlers for Mission Command deck
    ide_protocol.py        # IDE Protocol V1/V2 schemas (act, repo-map, conflicts)
    ide_websocket.py       # IDE WebSocket transport for VS and companion extensions
    openai_compat.py       # chat_completions(), completions() handlers
    models_endpoint.py     # list_models() handler
    middleware.py          # error_middleware, logging_middleware, CORS
  assets/
    ui/                    # Mission Command single-page dark-mode web application
      index.html           # Flight deck layout & workspace switcher
      styles.css           # Glassmorphic CSS design tokens
      app.js               # Vanilla JS reactive controller & WebSocket client
  grid/
    client.py              # GridDelegateBackend (gRPC with mTLS)
    failover.py            # FailoverBackend (primary -> fallback)
    lifecycle_client.py    # LifecycleManagementClient (trigger app restart)
    mas_agent.py           # NodeMasAgentClient (registers reverse-MCP with node-local MAS)
    serializer.py          # Serialization between engine and grid protobufs
  util/
    logging.py             # configure_logging() via structlog
    journal.py             # FileJournal with transactional snapshots & rollback
```

## Conventions

- **Python 3.12+**, src-layout (`[tool.setuptools.packages.find] where = ["src"]`).
- All domain models use `model_config = ConfigDict(frozen=True)`.
- `AuraCodeConfig` is intentionally mutable for runtime overrides.
- ABCs use `@abstractmethod`; no default implementations.
- `async def` throughout the engine and routing layers.
- structlog for structured logging.
- Adapters are subpackages under `adapters/` with a `register(registry)` entry point.
- Zero local vector database or ML embedding dependencies in AuraCode core (pure AST repo-map; neural search delegates to AuraXLM).
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
| `auraxlm_endpoint` | `str \| null` | `null` | AuraXLM neural retrieval endpoint |
| `grid_failover_to_local` | `bool` | `true` | Fall back to local if grid unavailable |
| `local_context_limit` | `int` | `100000` | Token threshold for grid delegation |
| `adapters` | `dict` | `{}` | Per-adapter configuration blocks |
| `grid_tls_cert` | `str \| null` | `null` | Client TLS certificate path (mTLS) |
| `grid_tls_key` | `str \| null` | `null` | Client TLS private key path |
| `grid_ca_cert` | `str \| null` | `null` | CA certificate path |
| `grid_server_name` | `str \| null` | `null` | Server name override for PKI |
| `grid_default_routing` | `str` | `"auto"` | Default grid routing preference |
| `default_sovereignty_enforcement` | `str` | `"none"` | Default sovereignty mode |
| `default_sensitivity_label` | `str \| null` | `null` | Default sensitivity label |
| `default_retrieval_mode` | `str` | `"disabled"` | Default retrieval mode |
| `default_execution_mode` | `str` | `"standard"` | Default execution mode |

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
| `REFACTOR` | `coder` | Code transformation with structural awareness |
| `REVIEW_DIFF` | `reasoning` | Diff-specific review, needs change context |
| `SECURITY_REVIEW` | `reasoning` | Security-focused analysis |
| `GENERATE_TESTS` | `coder` | Test generation from code context |
| `CROSS_FILE_EDIT` | `coder` | Multi-file coordinated modification |
| `ARCHITECTURE_TRACE` | `reasoning` | Cross-system architecture analysis |

Each intent also maps to a **capability profile** via `INTENT_CAPABILITY_MAP` in `intent_map.py`, specifying which backend features (e.g., `diff_aware`, `cross_file`, `security_analysis`) the intent benefits from.

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

AuraCode anchors the developer experience in the 4-tier AuraCore architecture:

```
[AuraCode] (Developer CLI / Headless Agent / Mission Command Deck)
    │
    ▼ exposes MCP capabilities via node-local MAS Coordinator (port 8740)
[AuraRouter] (Model Context Protocol / Federated MoE Routing Fabric)
    │
    ▼ delegates neural index queries (<2KB AST locally; full RAG in cloud)
[AuraXLM] (Domain-Specific Neural Codebase RAG & Model Foundry)
    │
    ▼ deploys .aurabundle artifacts & bare Git mirrors with cell governance
[AuraGrid] (Distributed Sovereign Grid / Auction-Allocated Compute Cells)
```

- **AuraRouter** (open source, Apache-2.0) — Multi-model MCP routing fabric embedded
  via `EmbeddedRouterBackend`. Dynamically classifies coding intents, evaluates
  sovereignty/latency constraints, and routes prompts to local or frontier models.
- **AuraXLM** (proprietary) — Neural retrieval and domain-specific code intelligence.
  AuraCode keeps its core free of local vector databases (AST map strictly under 2KB).
  When whole-codebase neural indexing is needed, AuraCode delegates retrieval to AuraXLM
  with structured fallbacks and commercial upsell notices.
- **AuraGrid** (proprietary) — Federated compute fabric. AuraCode delegates heavy inference
  via gRPC (`GridDelegateBackend`), distributes bare Git mirrors (`GridMirrorOrchestrator`),
  and runs pre-flight test suites before triggering live cell restarts.
- **Node-Local MAS Reverse-MCP Exposure** — When deployed across grid worker nodes, AuraCode
  runs `NodeMasAgentClient`, registering 21 FastMCP tools (including `auracode_act`,
  `auracode_repomap`, `auracode_conflicts`, `auracode_rollback`, `auracode_bundle_pack`)
  with the node-local Multi-Agent System (MAS coordinator at `http://127.0.0.1:8740`).
- **AI Prototype Generation & Human-in-the-Loop Governance** — This interconnected pipeline
  allows upstream AI orchestrators to autonomously generate prototypes via headless AuraCode
  MCP calls, package deterministic `.aurabundle` artifacts with cell governance constraints,
  and present architects with Mission Command diff review, conflict resolution, and
  transactional journal rollback before committing to the grid.

## Testing

```bash
# Full suite (710+ tests)
pytest tests/ -x -q

# By component
pytest tests/test_models.py -x -q          # Domain models
pytest tests/test_engine.py -x -q          # Engine, session, registry
pytest tests/test_preferences.py -x -q     # UserPreferences, PreferencesManager
pytest tests/test_adapters/ -x -q          # Adapter discovery, Claude Code, OpenCode
pytest tests/test_repl/ -x -q              # REPL console, slash commands
pytest tests/test_routing/ -x -q           # Embedded router, intent map, MCP catalog
pytest tests/test_shim/ -x -q              # API shim server
pytest tests/test_grid/ -x -q              # Grid client, failover, MAS agent
pytest tests/test_bundle/ -x -q            # .aurabundle packager and manifest validation
pytest tests/test_git/ -x -q               # Bare mirrors and scratch preflight
pytest tests/test_integration/ -x -q       # End-to-end bootstrap, CLI, ecosystem integration
```

All routing and grid tests are fully mocked — they pass without AuraRouter or AuraGrid installed.

## Dependencies

| Group | Packages |
|-------|----------|
| Core | `pydantic>=2.0`, `click>=8.0`, `structlog`, `PyYAML>=6.0`, `rich>=13.0` |
| `[api]` | `aiohttp>=3.9` |
| `[grid]` | `grpcio>=1.60`, `grpcio-tools>=1.60`, `protobuf>=4.25` |
| `[dev]` | `pytest>=8.0`, `pytest-asyncio`, `pytest-aiohttp`, `ruff`, plus `[all]` |

## Code Style

Enforced by **ruff** (linter + formatter). Configuration in `pyproject.toml`.

- **Line length: 100 characters** (`line-length = 100`). This applies to ALL file content — source, tests, docstrings, and inline comments. ruff enforces E501 with no per-file exceptions.
- `ruff-format` auto-wraps expressions and imports, but **does not reflow prose**. Docstrings and comments that exceed 100 chars must be wrapped manually.
- Pre-commit hooks run `ruff check` then `ruff-format` on every commit. Both must pass.

**Practical rules for test authors:**

1. Keep method docstrings short, or break them to multiple lines. A single-line docstring that reads at 100+ chars must become a multi-line docstring.
2. Long string literals in `assert` messages or function calls must be split with parenthesized continuation or assigned to a variable first.
3. Dict comprehensions with long key lists — split the `for ... in [...]` across two lines.
4. `pytest tests/ -x -q` runs a `test_lint.py` that invokes `ruff check` on the package; a failing lint is a failing test.
