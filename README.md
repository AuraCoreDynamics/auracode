# AuraCode

![Version](https://img.shields.io/badge/version-0.1.0-blue) ![Python](https://img.shields.io/badge/python-3.12%2B-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

**Terminal-native, vendor-agnostic AI coding assistant powered by Federated Mixture-of-Experts.**

AuraCode is a different kind of coding tool. Where other assistants lock you into a single model from a single vendor, AuraCode routes every request to the right model for the job — automatically, transparently, and under your control. A quick variable rename goes to a fast local model that responds in milliseconds. A complex architectural refactor goes to a frontier reasoning model. You don't choose; the system knows.

AuraCode speaks the languages your tools already speak. It exposes an OpenAI-compatible API, so any IDE extension — Copilot, Continue, Cody, or your own — works without modification. It provides CLI adapters that mirror the interfaces of Claude Code, Aider, and Codestral. Swap your backend without changing your workflow.

```
pip install -e ".[dev]"
auracode status
```

---

## Why Federated Mixture-of-Experts?

Every AI coding tool today makes you pick a model. You either get a fast model that hallucinates on hard problems, or a frontier model that's slow and expensive for simple tasks. You accept this tradeoff because the tools don't give you a choice.

AuraCode eliminates the tradeoff.

When you ask AuraCode to generate code, it classifies the *intent* of your request — is this code generation, explanation, review, planning? — and routes it to the model best suited for that class of work. Code generation goes to fast, specialized coding models. Planning and architecture go to deep reasoning models. Simple completions go to tiny local models that cost nothing and respond instantly.

This is Federated Mixture-of-Experts (FMoE): a routing fabric that treats models as specialists in a team, not as interchangeable commodities. The "federated" part means the models can live anywhere — on your laptop, on your team's GPU server, on a cloud API — and AuraCode stitches them into a single coherent assistant.

### What this means in practice

**Scenario: You're building a new REST API.**

You open your terminal and ask AuraCode to plan the endpoint structure. AuraCode routes this to a reasoning model — Claude Opus, DeepSeek-R1, or whatever frontier model your team has configured — because planning requires deep architectural thinking. The model returns a structured plan with endpoint definitions, data models, and error handling strategy.

You approve the plan. Now you ask AuraCode to generate the implementation. This time, AuraCode routes to a fast coding model — Sonnet, Codestral, or a local CodeLlama — because implementation from a clear spec is a well-bounded task. The code arrives in seconds, not minutes.

You review the generated code. You spot something odd in the error handling. You ask AuraCode to explain the pattern. AuraCode routes to the reasoning model again, because explanation requires understanding intent and context, not just pattern matching.

Three requests. Three different models. Zero configuration changes. You didn't think about model selection once.

**Scenario: You're on a plane with no internet.**

AuraCode doesn't stop working. It falls back to local models running on your hardware — Phi-3, Llama, Mistral, whatever you've downloaded. The experience degrades gracefully: planning might be slower, but code generation and completion still work at full speed because those local models are more than capable for bounded coding tasks. When you land and reconnect, AuraCode picks up cloud models again without any action on your part.

No other coding assistant offers this. They either require the cloud or they're local-only. AuraCode is both, automatically.

**Scenario: Your team works with classified data.**

Every prompt you send to a cloud API leaves your network. For teams handling proprietary algorithms, regulated data, or classified information, this is a non-starter. AuraCode, when connected to a local AuraRouter instance with on-premise models, keeps everything on your hardware. The inference happens locally. The prompts never leave. The model weights are yours to audit.

When the sensitivity allows it, you can configure AuraCode to route non-sensitive tasks (boilerplate generation, documentation, test scaffolding) to cloud models for speed, while keeping sensitive architectural and domain-specific work local. The routing is configurable per-intent, so you control exactly what crosses the network boundary.

**Scenario: You're reviewing a teammate's pull request with 47 changed files.**

You point AuraCode at the diff. With a local-only tool, the context window fills up fast — you get a shallow review of the first few files and nothing on the rest. With AuraCode, when the context exceeds your local model's capacity, the request automatically escalates to a model with a larger context window — or, if you have AuraGrid configured, distributes the review across multiple nodes that each handle a subset of files and merge findings. The result is a comprehensive review that would have taken you an hour, delivered in seconds.

---

## Quick Start

### Installation

```bash
# Core installation
pip install -e "."

# With development tools
pip install -e ".[dev]"

# With OpenAI-compatible API server
pip install -e ".[api]"

# With AuraGrid distributed compute support
pip install -e ".[grid]"

# Everything
pip install -e ".[all]"
```

### First Run

```bash
# Check that everything is wired up
auracode status

# List available models (depends on your AuraRouter configuration)
auracode models

# Launch the interactive REPL (default command)
auracode

# One-shot code generation via the Claude Code adapter
auracode claude do "Write a Python function that validates email addresses"

# Interactive conversation via Claude Code adapter
auracode claude chat

# Explain a file
auracode claude explain src/auracode/engine/core.py

# Review code
auracode claude review src/auracode/routing/embedded.py
```

### Serving IDE Extensions

AuraCode can act as a local OpenAI-compatible API server, allowing any IDE extension that supports custom endpoints to use your full model roster:

```bash
# Start the API shim on localhost:8741
auracode serve

# Custom port
auracode serve --port 9000
```

Then configure your IDE extension to point at `http://127.0.0.1:8741/v1` as the API base URL. The extension thinks it's talking to OpenAI. AuraCode intercepts every request and routes it through your configured model fabric.

**Endpoints served:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/chat/completions` | POST | Chat completions (streaming and non-streaming) |
| `/v1/completions` | POST | Legacy completions |
| `/v1/models` | GET | List available models |
| `/health` | GET | Health check |

### MCP Integration

AuraCode exposes itself as an MCP (Model Context Protocol) server, making its capabilities available to any MCP-compatible client — including other AuraCore tools.

**Exposed MCP tools:**
| Tool | Description |
|------|-------------|
| `auracode_generate` | Generate code with configurable intent, mode, and routing |
| `auracode_plan` | Plan architecture or implementation approach |
| `auracode_refactor` | Refactor code with diff-aware modifications |
| `auracode_review_diff` | Review code diffs for correctness and security |
| `auracode_security_review` | Security-focused code review |
| `auracode_explain` | Explain a file's contents |
| `auracode_review` | Review code in a file |
| `auracode_trace` | Show last execution trace metadata |
| `auracode_models` | List available models |

This means AuraRouter can discover and invoke AuraCode's specialized routing graphs as MCP services — a pattern called Reverse-MCP. AuraCode consumes AuraRouter for model routing; AuraRouter consumes AuraCode for coding-specific orchestration. Each tool becomes a composable building block in a larger system.

### Capability-Aware Execution

AuraCode supports typed execution policies that control how each request is processed:

**Execution Modes:**
| Mode | Description |
|------|-------------|
| `standard` | Default single-pass execution |
| `speculative` | Speculative verification with multiple models |
| `monologue` | Extended reasoning trace |

**Routing Preferences:**
| Preference | Behavior |
|------------|----------|
| `auto` | Let AuraCode decide based on context size and health |
| `prefer_local` | Prefer local models, fall back to cloud if needed |
| `require_local` | Local only — never send to cloud |
| `prefer_grid` | Prefer AuraGrid distributed execution |
| `require_grid` | Grid only — fail if grid unavailable |
| `require_verified` | Grid with verification — highest assurance |

**Sovereignty Controls:**
AuraCode supports sovereignty enforcement for teams handling sensitive data:
- `none` — No restrictions on execution location
- `warn` — Log when requests cross sovereignty boundaries
- `enforce` — Strictly enforce data locality; block cloud execution when `allow_cloud=false`

**Retrieval Mode:**
| Mode | Behavior |
|------|----------|
| `disabled` | No retrieval augmentation |
| `auto` | Use RAG when available |
| `required` | Fail or degrade visibly if RAG unavailable |

**REPL commands for FMoE controls:**
```
/mode [standard|speculative|monologue]   # Set execution mode
/sovereignty [none|warn|enforce]         # Set sovereignty posture
/retrieval [disabled|auto|required]      # Set retrieval mode
/trace                                    # Show last execution trace
/capabilities                            # Show backend capabilities
/status                                   # Shows mode, sovereignty, retrieval state
```

**Degradation is always explicit.** When a requested capability isn't available — e.g., speculative mode on a basic fabric, or retrieval-required on a backend without RAG — AuraCode records a typed `DegradationNotice` and surfaces it through `/trace` and `/status`. Silent fallback is treated as a bug.

### Grid PKI and Secure Transport

When connecting to AuraGrid, AuraCode supports full mTLS:

```yaml
grid_endpoint: grid.internal.corp:50051
grid_tls_cert: /etc/pki/auracode-client.crt
grid_tls_key: /etc/pki/auracode-client.key
grid_ca_cert: /etc/pki/corp-ca.crt
```

When TLS material is provided, AuraCode creates a secure gRPC channel. Without it, an insecure channel is used (suitable for development clusters).

### Policy Precedence

When execution controls can be set at multiple levels, the precedence order is:

1. **Per-request** (highest) — explicit `ExecutionPolicy` on `EngineRequest`
2. **Session** — REPL `/mode`, `/sovereignty`, `/retrieval` commands
3. **Preferences** — `~/.auracode/preferences.yaml`
4. **Config** — `auracode.yaml` defaults (lowest)

---

## Configuration

AuraCode loads configuration from the first file found in this order:

1. Path passed via `--config` flag
2. `./auracode.yaml` (current directory)
3. `~/.auracode.yaml` (home directory)
4. Built-in defaults

### Configuration Reference

```yaml
# Path to AuraRouter's config file. When set, AuraCode uses AuraRouter
# for model routing with full FMoE support.
router_config_path: null

# Default CLI adapter when none is specified.
default_adapter: opencode

# Logging verbosity: DEBUG, INFO, WARNING, ERROR.
log_level: INFO

# AuraGrid endpoint for distributed compute. When set, AuraCode can
# delegate large requests to grid nodes via gRPC.
grid_endpoint: null

# When true, AuraCode falls back to local models if the grid is unreachable.
# When false, grid-targeted requests fail if the grid is down.
grid_failover_to_local: true

# Token threshold for grid delegation. Requests whose estimated context
# exceeds this limit are automatically sent to the grid (if configured)
# rather than processed locally.
local_context_limit: 100000

# Per-adapter configuration. Keys are adapter names (e.g., "claude-code").
adapters: {}

# Grid TLS/PKI (mTLS for secure grid communication)
grid_tls_cert: null       # Client certificate path
grid_tls_key: null        # Client private key path
grid_ca_cert: null        # CA certificate path
grid_server_name: null    # Server name override for PKI

# Default execution policy
default_execution_mode: standard         # standard, speculative, monologue
default_sovereignty_enforcement: none    # none, warn, enforce
default_sensitivity_label: null          # e.g., "SECRET"
default_retrieval_mode: disabled         # disabled, auto, required
```

### User Preferences

AuraCode stores persistent user preferences in `~/.auracode/preferences.yaml`. Preferences survive across sessions and override config defaults where applicable.

```yaml
# ~/.auracode/preferences.yaml
default_adapter: opencode        # Adapter to use on startup
show_model_in_response: true     # Display which model handled each response
show_token_usage: false          # Show token counts in responses
history_limit: 100               # Max messages retained in session history
markdown_rendering: true         # Render markdown in REPL output
prefer_local: false              # Prefer local models over cloud
active_analyzer: null            # Active route analyzer (e.g., "auraxlm-moe")
default_execution_mode: standard # Execution mode (standard/speculative/monologue)
default_sovereignty_enforcement: none  # Sovereignty posture
default_sensitivity_label: null  # Sensitivity label
default_retrieval_mode: disabled # Retrieval mode (disabled/auto/required)
default_routing_preference: auto # Routing preference
```

Use the `/prefs` slash command in the REPL to view, set, or reset preferences interactively:

```
/prefs                    # Show all current preferences
/prefs set <key> <value>  # Set a preference
/prefs reset              # Reset all preferences to defaults
```

### Example Configurations

**Local-only (air-gapped, maximum privacy):**

```yaml
router_config_path: /etc/aurarouter/auraconfig.yaml
log_level: INFO
```

All inference stays on your machine. Configure AuraRouter with Ollama or llama.cpp backends. No data leaves your network, ever.

**Hybrid (local-first, cloud-assisted):**

```yaml
router_config_path: ~/.config/aurarouter/auraconfig.yaml
local_context_limit: 50000
```

AuraRouter's role chains handle the routing: fast local models for code generation and completion, cloud models for planning and review when you need deeper reasoning. Context stays local until it exceeds your local model's capacity.

**Team (grid-accelerated):**

```yaml
router_config_path: /opt/auracore/auraconfig.yaml
grid_endpoint: grid.internal.corp:50051
grid_failover_to_local: true
local_context_limit: 100000
```

Requests that exceed local capacity are delegated to your team's AuraGrid fabric — a distributed compute mesh that pools GPU resources across machines. If the grid is unavailable, AuraCode silently falls back to local execution. Your workflow never breaks.

---

## Architecture

```
                        +-----------------------+
                        |    Your Interface     |
                        | CLI / IDE / MCP / API |
                        +-----------+-----------+
                                    |
                        +-----------v-----------+
                        |       Adapters        |
                        | OpenCode (default)   |
                        |  Claude Code | Copilot|
                        |  Aider | Codestral   |
                        |  OpenAI API Shim     |
                        +-----------+-----------+
                                    |
                              EngineRequest
                                    |
                        +-----------v-----------+
                        |    AuraCodeEngine     |
                        |  Session Management   |
                        |  Intent Classification|
                        +-----------+-----------+
                                    |
                              Intent + Prompt
                                    |
                   +----------------v----------------+
                   |       Routing Backend           |
                   |  +---------------------------+  |
                   |  | EmbeddedRouterBackend     |  |
                   |  | (AuraRouter - local FMoE) |  |
                   |  +---------------------------+  |
                   |  | GridDelegateBackend        |  |
                   |  | (AuraGrid - distributed)   |  |
                   |  +---------------------------+  |
                   |  | FailoverBackend            |  |
                   |  | (Grid -> Local fallback)   |  |
                   |  +---------------------------+  |
                   +----------------+----------------+
                                    |
                         +----------v----------+
                         |   Model Providers   |
                         | Ollama | llama.cpp  |
                         | Claude | Gemini     |
                         | DeepSeek | Codestral|
                         | Local LoRA models   |
                         +---------------------+
```

### The Three Layers

**Adapters** are thin translators. They take input in one format (Claude Code's CLI, OpenAI's API, Copilot's ghost-text protocol) and convert it into an `EngineRequest`. They take an `EngineResponse` and convert it back. Adapters know nothing about models or routing — they only speak their interface's language.

**The Engine** is the orchestrator. It manages sessions (conversation history, file context), classifies the intent of each request, and delegates to the routing backend. The engine is async-first and adapter-agnostic — it doesn't know or care whether the request came from a CLI, an IDE, or an MCP tool.

**Routing Backends** select a model and execute inference. The `EmbeddedRouterBackend` wraps AuraRouter for local FMoE routing. The `GridDelegateBackend` sends requests to AuraGrid over gRPC. The `FailoverBackend` composes the two: try the grid first, fall back to local if it's unavailable or the request is small enough to handle locally.

### Intent-Based Routing

AuraCode classifies every request into one of seven intents:

| Intent | Routed To | Why |
|--------|-----------|-----|
| `generate_code` | Coder models | Bounded task, speed matters |
| `edit_code` | Coder models | Targeted modification, pattern recognition |
| `complete_code` | Coder models | Low-latency inline completion |
| `explain_code` | Reasoning models | Requires understanding intent and context |
| `review` | Reasoning models | Requires judgment and architectural awareness |
| `chat` | Reasoning models | Open-ended, benefits from depth |
| `plan` | Reasoning models | Architectural decomposition, frontier capability |

This mapping is configurable through AuraRouter's role chains. The defaults reflect a pragmatic split: coding tasks go to fast specialists, thinking tasks go to frontier generalists. When both are local models, the distinction is about which model's training data is better suited. When the split is local vs. cloud, it's also about cost — coding tasks stay free and fast, while the expensive cloud models are reserved for work that genuinely benefits from their capability.

---

## Adapters

### Available Adapters

| Adapter | Status | Description |
|---------|--------|-------------|
| `opencode` | **Default** | AuraCode-native adapter with clean markdown formatting. Powers the interactive REPL. |
| `claude-code` | Implemented | Conversational REPL, one-shot generation, explain, review |
| `openai-shim` | Implemented | OpenAI-compatible HTTP API for IDE extensions |
| `copilot` | Skeleton | GitHub Copilot CLI ghost-text and inline explanation |
| `aider` | Skeleton | Local file-system diffing, git commit generation, rollback |
| `codestral` | Skeleton | Specialized code-completion API endpoints |

### Writing a Custom Adapter

Adapters are self-contained subpackages under `src/auracode/adapters/`. Each must:

1. Subclass `BaseAdapter` from `auracode.adapters.base`
2. Implement `name`, `translate_request()`, `translate_response()`, and `get_cli_group()`
3. Expose a `register(registry)` function at the package level

The adapter discovery system scans all subpackages automatically — no central registration needed. Drop a new package in the `adapters/` directory and it's available on the next launch.

```python
# src/auracode/adapters/my_tool/__init__.py
from auracode.adapters.my_tool.adapter import MyToolAdapter

def register(registry):
    registry.register(MyToolAdapter())
```

---

## Interactive REPL

Running `auracode` with no subcommand launches the interactive REPL. The prompt displays the active adapter and analyzer:

```
opencode> help me plan a REST API
opencode:auraxlm-moe> explain src/auracode/engine/core.py
```

### Slash Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `/?` | Show available commands and usage hints |
| `/status` | | Show engine health, active adapter/analyzer, catalog counts |
| `/catalog` | `/models` | List the full catalog: models, services, and analyzers |
| `/analyzer` | | View or switch the active route analyzer |
| `/adapter` | | Switch or list adapters |
| `/claude` | | Switch to Claude Code adapter |
| `/copilot` | | Switch to Copilot adapter |
| `/aider` | | Switch to Aider adapter |
| `/codestral` | | Switch to Codestral adapter |
| `/context` | `/ctx` | Add or list context files |
| `/clear` | | Clear session history and/or context |
| `/prefs` | `/preferences` | View or set persistent preferences |
| `/explain` | | Explain a file (shortcut for `explain <file>` prompt) |
| `/review` | | Review a file (shortcut for `review <file>` prompt) |
| `/quit` | `/q`, `/exit` | Exit AuraCode |

### Catalog and Analyzers

The `/catalog` command (aliased as `/models`) displays the full roster of models, MCP services, and route analyzers available through the active routing backend. You can filter by kind:

```
/catalog            # Show everything
/catalog models     # Models only
/catalog services   # Services only
/catalog analyzers  # Analyzers only
```

Route analyzers control how requests are classified and routed. Switch analyzers with `/analyzer`:

```
/analyzer                  # Show current and available analyzers
/analyzer auraxlm-moe      # Switch to a specific analyzer
```

The active analyzer is persisted in user preferences and restored on next launch.

---

## Working With the Full AuraCore Stack

AuraCode is designed to work standalone with any OpenAI-compatible API. But its architecture is specifically designed to unlock capabilities that standalone operation cannot provide — capabilities that emerge when AuraCode is connected to the broader AuraCore fabric.

### AuraRouter: The Routing Brain

AuraRouter is the open-source multi-model routing fabric that AuraCode embeds as its primary backend. When AuraCode is configured with a `router_config_path`, every request flows through AuraRouter's intent-plan-execute loop:

1. **Intent analysis** classifies the request (is this code generation? explanation? planning?)
2. **Role chain resolution** determines which models to try, in what order
3. **Execution with fallback** tries models in sequence until one succeeds

AuraRouter handles the complexity of managing multiple model providers (Ollama, llama.cpp, Claude, Gemini, OpenAI-compatible endpoints) behind a single interface. You configure your model roster once in AuraRouter's `auraconfig.yaml` and every tool in the AuraCore ecosystem — including AuraCode — sees the same set of models.

### AuraGrid: Distributed Compute When You Need It

AuraCode works entirely on a single machine. But some tasks genuinely benefit from distributed execution — large codebase reviews where the context exceeds any single model's window, parallel code generation across multiple files, or simply offloading heavy inference from your development machine so it stays responsive.

When `grid_endpoint` is configured, AuraCode's `FailoverBackend` handles this transparently. Requests that exceed `local_context_limit` are serialized to protobuf and sent to the grid over gRPC with mTLS. The grid distributes the work across nodes that bid on it based on their available capacity — a low-powered node won't attempt work it can't handle.

The key design principle is graceful degradation. If the grid goes down, AuraCode falls back to local execution. Your workflow never breaks because the grid is unavailable. The grid is an accelerator, not a dependency.

AuraGrid's auction-based resource allocation also means you're never over-provisioning. Traditional cloud setups require you to guess how much GPU capacity you need and pay for idle time. The grid's market-based model means nodes only accept work they can handle efficiently, and work automatically flows to the most cost-effective node.

### AuraXLM: Knowledge-Augmented Intelligence

When AuraRouter is connected to AuraXLM — the decentralized mixture-of-experts system — AuraCode's capabilities extend further. AuraXLM provides retrieval-augmented generation (RAG) that grounds model responses in your actual codebase and documentation, not just the model's training data.

This means when you ask AuraCode to generate code that integrates with your existing system, the response reflects your actual API surfaces, naming conventions, and architectural patterns — because AuraXLM has indexed them. When you ask for a review, the reviewer understands your project's specific error handling strategy and dependency policies, not just generic best practices.

AuraXLM's Model Foundry takes this further: it can fine-tune small, fast models (Phi-3, Llama) on your project's codebase, creating domain specialists that understand your patterns at a level that general-purpose models never will. A 3.8B parameter model fine-tuned on your codebase can outperform a 70B general-purpose model for your specific project's coding tasks — and it runs locally, offline, for free.

The combination is powerful: AuraXLM's domain specialists handle the routine coding work (completions, boilerplate, pattern-following) at zero marginal cost, while frontier cloud models handle the genuinely novel work (architectural planning, complex refactoring, cross-cutting analysis). AuraCode's intent-based routing makes this split invisible to you.

---

## Project Layout

```
src/auracode/
  __init__.py              # Package root, version, public API
  app.py                   # Application bootstrap and wiring (returns 4-tuple)
  cli.py                   # Unified Click CLI entry point (repl is default command)
  mcp_server.py            # Reverse-MCP server (exposes tools to MCP clients)
  models/
    request.py             # EngineRequest, EngineResponse, RequestIntent, TokenUsage
    context.py             # SessionContext, FileContext
    config.py              # AuraCodeConfig
    preferences.py         # UserPreferences (persistent prefs model)
  adapters/
    base.py                # BaseAdapter ABC
    loader.py              # Auto-discovery of adapter subpackages
    opencode/              # OpenCode adapter — AuraCode-native (default)
      adapter.py           # OpenCodeAdapter
      formatter.py         # Clean markdown response formatting
    claude_code/           # Claude Code CLI adapter (implemented)
    openai_shim/           # OpenAI-compatible API adapter (implemented)
    copilot/               # GitHub Copilot adapter (skeleton)
    aider/                 # Aider adapter (skeleton)
    codestral/             # Codestral adapter (skeleton)
  repl/
    console.py             # AuraCodeConsole — interactive REPL loop
    commands.py            # Slash-command registry and built-in handlers
  routing/
    base.py                # BaseRouterBackend ABC, ModelInfo, ServiceInfo, AnalyzerInfo, RouteResult
    embedded.py            # EmbeddedRouterBackend (wraps AuraRouter)
    intent_map.py          # Intent-to-role mapping and context building
    mcp_catalog.py         # MCP tool catalog client
  engine/
    core.py                # AuraCodeEngine — central orchestrator
    session.py             # SessionManager — in-memory conversation state
    registry.py            # AdapterRegistry, BackendRegistry
    preferences.py         # PreferencesManager (load/save YAML prefs)
  shim/
    server.py              # aiohttp application factory and server launchers
    openai_compat.py       # /v1/chat/completions and /v1/completions handlers
    models_endpoint.py     # /v1/models handler
    middleware.py           # Error handling, logging, CORS
  grid/
    client.py              # GridDelegateBackend (gRPC to AuraGrid)
    failover.py            # FailoverBackend (grid -> local fallback)
    serializer.py          # Request/response serialization for gRPC
    messages.py            # Pure Python proto message classes
    proto/
      auracode_grid.proto  # Protobuf service definition
  util/
    logging.py             # structlog configuration
tests/
  conftest.py              # Shared fixtures, mock backends
  test_models.py           # Domain model tests
  test_engine.py           # Engine, session, registry tests
  test_preferences.py      # UserPreferences and PreferencesManager tests
  test_adapters/           # Adapter discovery, Claude Code, and OpenCode tests
  test_repl/               # REPL console and slash-command tests
  test_routing/            # Embedded router, intent mapping, MCP catalog tests
  test_shim/               # API shim server tests
  test_grid/               # Grid client and failover tests
  test_integration/        # End-to-end bootstrap, CLI, and full-path tests
```

## Development

```bash
# Install with all optional dependencies
pip install -e ".[dev]"

# Run the full test suite
pytest tests/ -x -q

# Run specific test groups
pytest tests/test_models.py -x -q
pytest tests/test_adapters/ -x -q
pytest tests/test_integration/ -x -q
```

## License

MIT
