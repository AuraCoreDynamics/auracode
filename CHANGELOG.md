# Changelog

All notable changes to AuraCode are documented here.

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
