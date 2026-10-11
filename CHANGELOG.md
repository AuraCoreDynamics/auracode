# Changelog

All notable changes to AuraCode are documented here.

## [Unreleased] — 2026-04-26

### Added
- **Mission Command Operations Deck & Telemetry Engine**:
  - `auracode ui` launching a dark-mode glassmorphic single-page operations dashboard on port 8741.
  - `MissionEventBus` broadcasting real-time agent execution, verification, and git events over WebSockets (`/api/events`).
  - Fleet management and conflict resolution REST endpoints (`/api/fleet/workspaces`, `/api/fleet/conflicts`, `/api/fleet/rollback`).
- **Autonomous Self-Healing Agent Loop & Journal Rollback**:
  - `AgenticExecutionLoop` executing multi-turn code generation with test verification gates and bounded 3-turn remediation budget.
  - `FileJournal` snapshot checkpoints and one-click transactional rollback restoring exact pre-run SHA-256 states.
  - REPL slash commands: `/act`, `/verify`, `/rollback`.
- **Zero-Vector Deterministic AST Repo-Map & AuraXLM Delegation**:
  - `RepoMapBuilder` extracting classes, functions, and signatures under strict 2KB context window budget without vector databases or embedding overhead.
  - `AuraXlmRetrievalClient` delegating neural codebase retrieval to enterprise AuraXLM on AuraGrid with typed `DegradationNotice` fallback.
  - REPL slash command: `/repomap`.
- **Collaborative Git Engine & Pre-Flight Validation**:
  - `GitMirrorPoller` pre-flight verification gate testing pushes in scratch clones before triggering AuraGrid application restarts.
  - `MergeConflictResolver` parsing Git conflict markers (`<<<<<<<`, `|||||||`, `=======`, `>>>>>>>`) and synthesizing semantic conflict-free merges.
  - `CommitSynthesizer` generating Conventional Commit titles and bodies from staged diffs.
  - REPL slash commands: `/conflicts`, `/resolve-conflicts`, `/commit`.
- **Application Packaging & Cell Governance (`.aurabundle`)**:
  - `BundlePackager` creating and inspecting `.aurabundle` tar.gz archives with SHA-256 digests.
  - `ManifestValidator` enforcing schema and path traversal security on `app.manifest.json`.
  - `CellGovernanceSpec` declaring resource limits, network isolation, and cell affinity.
  - CLI `auracode bundle [pack|validate|inspect]` and REPL slash command `/bundle`.
- **Node-Local MAS and Reverse-MCP Grid Exposure**:
  - Expanded FastMCP catalog with 8 new tools (`auracode_act`, `auracode_repomap`,
    `auracode_conflicts`, `auracode_resolve_conflicts`, `auracode_rollback`,
    `auracode_synthesize_commit`, `auracode_bundle_pack`, `auracode_bundle_validate`) for a total
    of 21 registered MCP tools.
  - `NodeMasAgentClient` registering reverse-MCP tools with node-local MAS at port 8740.
  - REPL slash command `/mas-status` for inspecting MAS agent health and capabilities.
- **Multi-Project Mission Command Deck**:
  - `FleetWorkspaceManager` managing multi-repository metadata and state across disk workspaces.
  - REST endpoints `GET/POST /api/fleet/workspaces`, `DELETE /api/fleet/workspaces/{id}` with
    `--auth-token` token authentication middleware gate.
  - Mission Command UI header dropdown workspace switcher, registration modal, and card actions.
  - CLI commands `auracode fleet [add|remove|list]`.
- **Distributed Git Bare Mirrors on AuraGrid**:
  - `GridMirrorOrchestrator` initializing bare mirrors tracking `main` across grid nodes.
  - Scratch clone pre-flight test runner with duration telemetry and guaranteed sandbox cleanup.
  - REPL slash command `/grid-mirror [init|sync|status]`.
- **IDE Bridges (Visual Studio V2 & Spyder Companion)**:
  - IDE Protocol V2 schemas (`ActRequest`, `ActProgress`, `ResolveConflictRequest`, etc.).
  - `SpyderAuraCodeBridge` companion adapter for Spyder IDE Python environments.
  - Comprehensive integration documentation in `docs/IDE_INTEGRATION.md`.
- **AuraXLM Commercial Conversion Funnel**:
  - AST context truncation detection in `RepoMapBuilder` injecting commercial AuraXLM footer.
  - REPL slash command `/xlm-benchmark` measuring local AST vs. remote neural retrieval.
- **AuraRouter catalog push-registration** — `CatalogRegistrar` class in `catalog_registration.py`:
  - Registers `auracode-mcp` as a service artifact with capabilities (`code-generation`, `code-review`, `code-refactoring`, `code-explanation`, `security-review`) and intents (`GENERATE_CODE`, `EDIT_CODE`, `REVIEW`, `EXPLAIN_CODE`)
  - Exponential-backoff retry (1s → 60s cap), configurable `max_retries` (0 = unlimited)
  - 5-minute heartbeat re-registration loop with broad exception guard (no silent task death)
  - `auracode serve` wires registration on startup and deregistration on shutdown
  - `asyncio.create_task()` with exception handler (replaces `ensure_future`)
- **`aurarouter_url` config field** on `AuraCodeConfig` — defaults to `None` (opt-in; prevents localhost retry-spam on hosts without AuraRouter)

### Changed
- `catalog_registration.py` `DEFAULT_AURAROUTER_URL` changed from `"http://localhost:8321"` to `None`
- `AuraCodeConfig.aurarouter_url` default changed from `"http://localhost:8321"` to `None`



### Added
- **Copilot adapter**: Full implementation with suggest, explain, commit commands; intent mappings to GENERATE_CODE and EXPLAIN_CODE
- **Aider adapter**: Full implementation with code, ask, architect commands; intent mappings to EDIT_CODE, CHAT, PLAN
- **Codestral adapter**: Full implementation with complete, fill, chat commands; FIM-style prefix/suffix support; intent mappings to COMPLETE_CODE, GENERATE_CODE, CHAT
- **Grid RPC transport**: `GridDelegateBackend` fully implemented with gRPC channel management, mTLS support, Execute/ListModels/HealthCheck RPCs, and `FailoverBackend` for grid-to-local automatic fallback
- **Claude Code CLI wiring**: All Claude Code CLI commands (do, explain, review, chat) wired through `create_application()` bootstrap and `AuraCodeEngine.execute()` pipeline
- **End-to-end integration tests**: `test_full_stack.py` validating all 5 adapter discovery, engine execution flow, grid serialization roundtrips, and placeholder removal

### Changed
- Copilot, Aider, and Codestral CLI commands now execute through the engine instead of returning placeholder responses
- All adapter CLIs follow the same bootstrap pattern as Claude Code CLI (import `create_application`, resolve adapter, run async execute)
- Grid client no longer stubbed — `_ensure_channel()`, `_call_execute()`, `_call_list_models()`, `_call_health_check()` are fully implemented with lazy grpc imports

### Removed
- `_placeholder_response()` function removed from copilot/cli.py, aider/cli.py, and codestral/cli.py

## [0.1.0] — 2026-03-23

### Added
- **Core engine**: Async request/response pipeline with session management and structured logging
- **Domain models**: Pydantic v2 frozen models — `EngineRequest`, `EngineResponse`, `RequestIntent`, `SessionContext`, `FileContext`, `TokenUsage`, `FileArtifact`
- **Adapter framework**: Auto-discovery via package scanning, `BaseAdapter` ABC
- **OpenCode adapter**: AuraCode-native CLI persona (default adapter)
- **Claude Code adapter**: CLI skin mimicking Claude Code's conversational interface
- **OpenAI API shim**: Local HTTP server (`/v1/chat/completions`, `/v1/models`) for IDE extension compatibility
- **Skeleton adapters**: Copilot, Aider, Codestral (ready for implementation)
- **Interactive REPL**: Rich terminal console with slash commands, adapter switching, context management
- **Slash commands**: `/help`, `/catalog`, `/models`, `/analyzer`, `/adapter`, `/claude`, `/copilot`, `/aider`, `/codestral`, `/context`, `/clear`, `/explain`, `/review`, `/prefs`, `/quit`
- **Embedded AuraRouter backend**: Wraps AuraRouter's `ComputeFabric` with intent-to-role mapping
- **AuraGrid delegation**: gRPC client with mTLS support and `FailoverBackend` (grid → local automatic fallback)
- **Catalog-aware routing**: `ServiceInfo`, `AnalyzerInfo` models; `/catalog` shows models, services, and analyzers; `/analyzer` to view/switch active route analyzer
- **User preferences**: Persistent `~/.auracode/preferences.yaml` with `PreferencesManager`; `/prefs` command for viewing/setting
- **Reverse-MCP server**: Exposes `auracode_generate`, `auracode_explain`, `auracode_review`, `auracode_models` as MCP tools
- **Intent-based routing**: Automatic classification of prompts into 7 intent types routed to appropriate model roles
- **PyPI packaging**: `pyproject.toml` with optional dependency groups (`[api]`, `[grid]`, `[all]`, `[dev]`), typed package marker, MANIFEST.in
- **CI/CD**: GitHub Actions workflows for testing (Python 3.12/3.13), linting (ruff), and PyPI publishing (trusted publisher)
