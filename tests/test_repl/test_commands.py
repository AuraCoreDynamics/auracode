"""Tests for REPL slash commands."""

from __future__ import annotations

import pytest

from auracode.repl.commands import all_commands, get, register_builtin_commands
from auracode.repl.console import AuraCodeConsole


@pytest.fixture(autouse=True)
def _setup_commands():
    """Ensure commands are registered before each test."""
    register_builtin_commands()


class TestCommandRegistry:
    """Slash command registration and lookup."""

    def test_help_registered(self):
        assert get("help") is not None

    def test_aliases_resolve(self):
        assert get("h") is get("help")
        assert get("?") is get("help")
        assert get("q") is get("quit")
        assert get("exit") is get("quit")
        assert get("ctx") is get("context")

    def test_unknown_returns_none(self):
        assert get("nonexistent") is None

    def test_all_commands_deduplicated(self):
        cmds = all_commands()
        names = [c.name for c in cmds]
        assert len(names) == len(set(names))

    def test_expected_commands_exist(self):
        expected = {
            "help",
            "status",
            "catalog",
            "analyzer",
            "adapter",
            "claude",
            "copilot",
            "aider",
            "codestral",
            "context",
            "clear",
            "explain",
            "review",
            "quit",
            "prefs",
            "mode",
            "sovereignty",
            "retrieval",
            "trace",
            "capabilities",
            "permissions",
            "spend",
        }
        actual = {c.name for c in all_commands()}
        assert expected == actual

    def test_models_alias_resolves_to_catalog(self):
        assert get("models") is get("catalog")


class TestHelpCommand:
    """The /help command."""

    async def test_help_lists_commands(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/help")
        assert "/help" in result
        assert "/quit" in result
        assert "/adapter" in result
        assert "/claude" in result

    async def test_help_alias(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/h")
        assert "/help" in result


class TestAdapterSwitching:
    """Adapter switching via /adapter and shortcuts."""

    async def test_switch_adapter(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/adapter copilot")
        assert "copilot" in result.lower()
        assert console.active_adapter.name == "copilot"

    async def test_switch_back(self, console: AuraCodeConsole):
        await console._dispatch_command("/adapter copilot")
        await console._dispatch_command("/adapter claude-code")
        assert console.active_adapter.name == "claude-code"

    async def test_claude_shortcut(self, console: AuraCodeConsole):
        await console._dispatch_command("/copilot")
        assert console.active_adapter.name == "copilot"
        await console._dispatch_command("/claude")
        assert console.active_adapter.name == "claude-code"

    async def test_unknown_adapter(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/adapter nonexistent")
        assert "Unknown adapter" in result

    async def test_list_adapters(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/adapter")
        assert "opencode" in result
        assert "copilot" in result
        assert "Active adapter:" in result


class TestStatusCommand:
    """The /status command."""

    async def test_status_shows_info(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/status")
        assert "AuraCode Status" in result
        assert "opencode" in result
        assert "healthy" in result
        assert "models" in result.lower()

    async def test_status_shows_catalog_counts(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/status")
        assert "Catalog:" in result
        assert "2 models" in result
        assert "0 services" in result
        assert "0 analyzers" in result

    async def test_status_shows_active_analyzer(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/status")
        assert "Active analyzer: none" in result


class TestModelsCommand:
    """The /models command (alias of /catalog)."""

    async def test_models_lists_available(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/models")
        assert "mock-local" in result
        assert "mock-cloud" in result


class TestContextCommand:
    """The /context command for managing file context."""

    async def test_no_context_initially(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/context")
        assert "No context files" in result

    async def test_add_context_file(self, console: AuraCodeConsole, tmp_path):
        test_file = tmp_path / "example.py"
        test_file.write_text("print('hello')")
        result = await console._dispatch_command(f"/context {test_file}")
        assert "Added" in result
        assert "example.py" in result

    async def test_list_context_after_add(self, console: AuraCodeConsole, tmp_path):
        test_file = tmp_path / "demo.py"
        test_file.write_text("x = 1")
        await console._dispatch_command(f"/context {test_file}")
        result = await console._dispatch_command("/context")
        assert "demo.py" in result

    async def test_nonexistent_file(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/context /no/such/file.py")
        assert "not found" in result.lower()

    async def test_context_alias(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/ctx")
        assert "No context files" in result


class TestClearCommand:
    """The /clear command."""

    async def test_clear_all(self, console: AuraCodeConsole):
        console.session_history.append({"role": "user", "content": "test"})
        from auracode.models.context import FileContext

        console.context_files.append(FileContext(path="x.py", content="x"))
        result = await console._dispatch_command("/clear")
        assert console.session_history == []
        assert console.context_files == []
        assert "cleared" in result.lower()

    async def test_clear_history_only(self, console: AuraCodeConsole):
        console.session_history.append({"role": "user", "content": "test"})
        from auracode.models.context import FileContext

        console.context_files.append(FileContext(path="x.py", content="x"))
        await console._dispatch_command("/clear history")
        assert console.session_history == []
        assert len(console.context_files) == 1

    async def test_clear_context_only(self, console: AuraCodeConsole):
        console.session_history.append({"role": "user", "content": "test"})
        from auracode.models.context import FileContext

        console.context_files.append(FileContext(path="x.py", content="x"))
        await console._dispatch_command("/clear context")
        assert len(console.session_history) == 1
        assert console.context_files == []


class TestExplainReviewShortcuts:
    """The /explain and /review slash commands."""

    async def test_explain_sends_prompt(self, console: AuraCodeConsole, mock_backend):
        result = await console._dispatch_command("/explain main.py")
        assert result is not None
        assert mock_backend.last_intent.value == "explain_code"

    async def test_review_sends_prompt(self, console: AuraCodeConsole, mock_backend):
        result = await console._dispatch_command("/review server.py")
        assert result is not None
        assert mock_backend.last_intent.value == "review"

    async def test_explain_no_file(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/explain")
        assert "Usage" in result

    async def test_review_no_file(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/review")
        assert "Usage" in result


class TestQuitCommand:
    """The /quit command."""

    async def test_quit_sets_running_false(self, console: AuraCodeConsole):
        console.running = True
        await console._dispatch_command("/quit")
        assert console.running is False

    async def test_exit_alias(self, console: AuraCodeConsole):
        console.running = True
        await console._dispatch_command("/exit")
        assert console.running is False

    async def test_q_alias(self, console: AuraCodeConsole):
        console.running = True
        await console._dispatch_command("/q")
        assert console.running is False


class TestPrefsCommand:
    """The /prefs command."""

    async def test_prefs_no_manager(self, console: AuraCodeConsole):
        """Returns message when no preferences manager is set."""
        console.preferences_manager = None
        result = await console._dispatch_command("/prefs")
        assert "not available" in result.lower()

    async def test_prefs_show_all(self, console: AuraCodeConsole, tmp_path):
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)
        result = await console._dispatch_command("/prefs")
        assert "User Preferences:" in result
        assert "default_adapter" in result
        assert "opencode" in result

    async def test_prefs_set(self, console: AuraCodeConsole, tmp_path):
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)
        result = await console._dispatch_command("/prefs set history_limit 50")
        assert "50" in result
        assert console.preferences_manager.get("history_limit") == 50

    async def test_prefs_set_unknown_key(self, console: AuraCodeConsole, tmp_path):
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)
        result = await console._dispatch_command("/prefs set nonexistent value")
        assert "Unknown" in result

    async def test_prefs_set_missing_args(self, console: AuraCodeConsole, tmp_path):
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)
        result = await console._dispatch_command("/prefs set")
        assert "Usage" in result

    async def test_prefs_reset(self, console: AuraCodeConsole, tmp_path):
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)
        # Change something first
        console.preferences_manager.set("history_limit", "50")
        assert console.preferences_manager.get("history_limit") == 50
        result = await console._dispatch_command("/prefs reset")
        assert "reset" in result.lower()
        assert console.preferences_manager.get("history_limit") == 100

    async def test_prefs_alias(self, console: AuraCodeConsole, tmp_path):
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)
        result = await console._dispatch_command("/preferences")
        assert "User Preferences:" in result


class TestCatalogCommand:
    """The /catalog command."""

    async def test_catalog_shows_all_sections(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/catalog")
        assert "Models (2):" in result
        assert "Services (0):" in result
        assert "Route Analyzers (0):" in result

    async def test_catalog_models_filter(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/catalog models")
        assert "Models (2):" in result
        assert "mock-local" in result
        assert "Services" not in result
        assert "Route Analyzers" not in result

    async def test_catalog_services_filter(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/catalog services")
        assert "Services (0):" in result
        assert "(none)" in result
        assert "Models" not in result

    async def test_catalog_analyzers_filter(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/catalog analyzers")
        assert "Route Analyzers (0):" in result
        assert "(none)" in result
        assert "Models" not in result

    async def test_models_alias_works(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/models")
        assert "Models (2):" in result
        assert "Services (0):" in result

    async def test_empty_catalog_shows_none(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/catalog")
        # services and analyzers sections should show (none)
        lines = result.split("\n")
        # Find "(none)" markers — should appear for services and analyzers
        none_count = sum(1 for line in lines if "(none)" in line)
        assert none_count == 2  # services + analyzers

    async def test_catalog_with_services_and_analyzers(self, console: AuraCodeConsole):
        """Test catalog with non-empty services and analyzers."""
        from auracode.routing.base import AnalyzerInfo, ServiceInfo

        async def mock_list_services():
            return [
                ServiceInfo(
                    service_id="mcp-github",
                    display_name="GitHub MCP",
                    provider="github",
                    tools=["search", "pr_create"],
                    status="active",
                ),
            ]

        async def mock_list_analyzers():
            return [
                AnalyzerInfo(
                    analyzer_id="cost-optimizer",
                    display_name="Cost Optimizer",
                    description="Minimizes inference cost",
                    is_active=True,
                ),
            ]

        console.engine.router.list_services = mock_list_services
        console.engine.router.list_analyzers = mock_list_analyzers

        result = await console._dispatch_command("/catalog")
        assert "Services (1):" in result
        assert "mcp-github" in result
        assert "GitHub MCP" in result
        assert "[active]" in result
        assert "(2 tools)" in result
        assert "Route Analyzers (1):" in result
        assert "cost-optimizer" in result
        assert "(active)" in result
        assert "Minimizes inference cost" in result


class TestAnalyzerCommand:
    """The /analyzer command."""

    async def test_analyzer_lists_available(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/analyzer")
        assert "Active analyzer: none" in result
        assert "legacy role-chain mode" in result

    async def test_analyzer_no_analyzers_available(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/analyzer")
        assert "No analyzers available." in result

    async def test_analyzer_set_fails_by_default(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/analyzer some-analyzer")
        assert "Failed to set analyzer" in result
        assert "Use /analyzer" in result

    async def test_analyzer_set_succeeds(self, console: AuraCodeConsole):
        """Test setting an analyzer when backend supports it."""

        async def mock_set_active(analyzer_id):
            return True

        console.engine.router.set_active_analyzer = mock_set_active
        result = await console._dispatch_command("/analyzer my-analyzer")
        assert "Active analyzer: my-analyzer" in result
        assert console._active_analyzer_id == "my-analyzer"

    async def test_analyzer_shows_active(self, console: AuraCodeConsole):
        """Test /analyzer shows the active analyzer when one is set."""
        from auracode.routing.base import AnalyzerInfo

        async def mock_get_active():
            return AnalyzerInfo(
                analyzer_id="intent-v2",
                display_name="Intent Analyzer v2",
                is_active=True,
            )

        async def mock_list_analyzers():
            return [
                AnalyzerInfo(
                    analyzer_id="intent-v2",
                    display_name="Intent Analyzer v2",
                    is_active=True,
                ),
                AnalyzerInfo(
                    analyzer_id="cost-opt",
                    display_name="Cost Optimizer",
                    is_active=False,
                ),
            ]

        console.engine.router.get_active_analyzer = mock_get_active
        console.engine.router.list_analyzers = mock_list_analyzers

        result = await console._dispatch_command("/analyzer")
        assert "Active analyzer: intent-v2" in result
        assert "Intent Analyzer v2" in result
        assert "Available analyzers:" in result
        assert "cost-opt" in result

    async def test_analyzer_persists_preference(self, console: AuraCodeConsole, tmp_path):
        """Test that switching analyzer persists to preferences."""
        from auracode.engine.preferences import PreferencesManager

        prefs_file = tmp_path / "prefs.yaml"
        console.preferences_manager = PreferencesManager(prefs_path=prefs_file)

        async def mock_set_active(analyzer_id):
            return True

        console.engine.router.set_active_analyzer = mock_set_active
        await console._dispatch_command("/analyzer my-analyzer")
        assert console.preferences_manager.get("active_analyzer") == "my-analyzer"


class TestUnknownCommand:
    """Unknown slash commands."""

    async def test_unknown_command_message(self, console: AuraCodeConsole):
        result = await console._dispatch_command("/foobar")
        assert "Unknown command" in result
        assert "/help" in result
