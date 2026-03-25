# Changelog

All notable changes to AuraCode are documented here.

## [0.2.0] — 2026-03-24

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
