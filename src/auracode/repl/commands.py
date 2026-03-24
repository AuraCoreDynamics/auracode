"""Slash-command registry for the interactive REPL."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.repl.console import AuraCodeConsole


@dataclass
class SlashCommand:
    """A registered slash command."""

    name: str
    description: str
    handler: Callable[[AuraCodeConsole, str], Awaitable[str | None]]
    aliases: list[str] = field(default_factory=list)


# Global command registry — populated by register_builtin_commands().
_COMMANDS: dict[str, SlashCommand] = {}


def register(cmd: SlashCommand) -> None:
    """Register a slash command (and its aliases) in the global registry."""
    _COMMANDS[cmd.name] = cmd
    for alias in cmd.aliases:
        _COMMANDS[alias] = cmd


def get(name: str) -> SlashCommand | None:
    """Look up a slash command by name or alias (without the leading /)."""
    return _COMMANDS.get(name)


def all_commands() -> list[SlashCommand]:
    """Return deduplicated list of all registered commands."""
    seen: set[str] = set()
    result: list[SlashCommand] = []
    for cmd in _COMMANDS.values():
        if cmd.name not in seen:
            seen.add(cmd.name)
            result.append(cmd)
    return result


# ── Built-in command handlers ──────────────────────────────────────────


async def _handle_help(console: AuraCodeConsole, args: str) -> str | None:
    """Show available slash commands."""
    lines = ["", "Available commands:"]
    for cmd in all_commands():
        aliases = f"  (aliases: {', '.join('/' + a for a in cmd.aliases)})" if cmd.aliases else ""
        lines.append(f"  /{cmd.name:<14} {cmd.description}{aliases}")
    lines.append("")
    lines.append("Type any text without a / prefix to send it as a prompt.")
    lines.append("Prefix a prompt with a verb to hint intent:")
    lines.append("  explain <file>   review <file>   plan <description>   edit <description>")
    return "\n".join(lines)


async def _handle_status(console: AuraCodeConsole, args: str) -> str | None:
    """Show engine health."""
    healthy = await console.engine.router.health_check()
    models = await console.engine.router.list_models()
    services = await console.engine.router.list_services()
    analyzers = await console.engine.router.list_analyzers()
    active_analyzer = await console.engine.router.get_active_analyzer()
    adapter_name = console.active_adapter.name if console.active_adapter else "none"
    analyzer_name = active_analyzer.analyzer_id if active_analyzer else "none"
    lines = [
        "",
        "AuraCode Status",
        f"  Active adapter:  {adapter_name}",
        f"  Active analyzer: {analyzer_name}",
        f"  Router:          {'healthy' if healthy else 'unavailable'}",
        f"  Catalog:         {len(models)} models, "
        f"{len(services)} services, {len(analyzers)} analyzers",
        f"  Session history: {len(console.session_history)} messages",
    ]
    return "\n".join(lines)


async def _handle_catalog(console: AuraCodeConsole, args: str) -> str | None:
    """List the full catalog: models, services, and analyzers."""
    filter_kind = args.strip().lower() if args.strip() else None
    lines = []

    if filter_kind in (None, "models"):
        models = await console.engine.router.list_models()
        lines.append(f"Models ({len(models)}):")
        if models:
            for m in models:
                tags = f" [{', '.join(m.tags)}]" if m.tags else ""
                lines.append(f"  {m.model_id} ({m.provider}){tags}")
        else:
            lines.append("  (none)")

    if filter_kind in (None, "services"):
        services = await console.engine.router.list_services()
        lines.append(f"\nServices ({len(services)}):")
        if services:
            for s in services:
                status = f" [{s.status}]" if s.status != "registered" else ""
                tools_count = f" ({len(s.tools)} tools)" if s.tools else ""
                lines.append(f"  {s.service_id} — {s.display_name}{status}{tools_count}")
        else:
            lines.append("  (none)")

    if filter_kind in (None, "analyzers"):
        analyzers = await console.engine.router.list_analyzers()
        lines.append(f"\nRoute Analyzers ({len(analyzers)}):")
        if analyzers:
            for a in analyzers:
                active = " (active)" if a.is_active else ""
                lines.append(f"  {a.analyzer_id} — {a.display_name}{active}")
                if a.description:
                    lines.append(f"    {a.description}")
        else:
            lines.append("  (none)")

    return "\n".join(lines)


async def _handle_analyzer(console: AuraCodeConsole, args: str) -> str | None:
    """View or switch the active route analyzer."""
    name = args.strip()
    if not name:
        active = await console.engine.router.get_active_analyzer()
        analyzers = await console.engine.router.list_analyzers()
        lines = [""]
        if active:
            lines.append(f"Active analyzer: {active.analyzer_id} — {active.display_name}")
        else:
            lines.append("Active analyzer: none (legacy role-chain mode)")
        lines.append("")
        if analyzers:
            lines.append("Available analyzers:")
            for a in analyzers:
                marker = " (active)" if a.is_active else ""
                lines.append(f"  {a.analyzer_id} — {a.display_name}{marker}")
        else:
            lines.append("No analyzers available.")
        return "\n".join(lines)

    success = await console.engine.router.set_active_analyzer(name)
    if success:
        if hasattr(console, "_active_analyzer_id"):
            console._active_analyzer_id = name
        if hasattr(console, "preferences_manager") and console.preferences_manager:
            try:
                console.preferences_manager.set("active_analyzer", name)
                console.preferences_manager.save()
            except Exception:
                pass
        return f"Active analyzer: {name}"
    else:
        return f"Failed to set analyzer '{name}'. Use /analyzer to see available options."


async def _handle_adapter(console: AuraCodeConsole, args: str) -> str | None:
    """Switch the active adapter/vendor persona."""
    name = args.strip()
    if not name:
        available = console.adapter_registry.list_adapters()
        current = console.active_adapter.name if console.active_adapter else "none"
        lines = ["", f"Active adapter: {current}", "Available adapters:"]
        for a in available:
            marker = " (active)" if a == current else ""
            lines.append(f"  {a}{marker}")
        lines.append("")
        lines.append("Switch with: /adapter <name>")
        return "\n".join(lines)

    adapter = console.adapter_registry.get(name)
    if adapter is None:
        available = console.adapter_registry.list_adapters()
        return f"Unknown adapter '{name}'. Available: {', '.join(available)}"

    console.active_adapter = adapter
    # Persist preference if preferences manager is available.
    if hasattr(console, "preferences_manager") and console.preferences_manager is not None:
        try:
            console.preferences_manager.set("default_adapter", adapter.name)
        except Exception:
            pass  # Non-critical: don't let pref save failure block switching.
    return f"Switched to {adapter.name}."


async def _handle_claude(console: AuraCodeConsole, args: str) -> str | None:
    """Switch to Claude Code adapter."""
    return await _handle_adapter(console, "claude-code")


async def _handle_copilot(console: AuraCodeConsole, args: str) -> str | None:
    """Switch to Copilot adapter."""
    return await _handle_adapter(console, "copilot")


async def _handle_aider(console: AuraCodeConsole, args: str) -> str | None:
    """Switch to Aider adapter."""
    return await _handle_adapter(console, "aider")


async def _handle_codestral(console: AuraCodeConsole, args: str) -> str | None:
    """Switch to Codestral adapter."""
    return await _handle_adapter(console, "codestral")


async def _handle_context(console: AuraCodeConsole, args: str) -> str | None:
    """Add or list context files."""
    from pathlib import Path

    from auracode.models.context import FileContext

    path_str = args.strip()
    if not path_str:
        if not console.context_files:
            return "No context files loaded. Use: /context <path>"
        lines = ["", "Context files:"]
        for fc in console.context_files:
            size = f" ({len(fc.content)} chars)" if fc.content else " (no content)"
            lines.append(f"  {fc.path}{size}")
        return "\n".join(lines)

    p = Path(path_str)
    if not p.is_file():
        return f"File not found: {path_str}"
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Cannot read {path_str}: {e}"
    fc = FileContext(
        path=str(p.resolve()),
        content=content,
        language=p.suffix.lstrip(".") or None,
    )
    console.context_files.append(fc)
    return f"Added {p.name} ({len(content)} chars) to context."


async def _handle_clear(console: AuraCodeConsole, args: str) -> str | None:
    """Clear session history and context."""
    what = args.strip().lower()
    if what == "context":
        console.context_files.clear()
        return "Context files cleared."
    elif what == "history":
        console.session_history.clear()
        return "Session history cleared."
    else:
        console.context_files.clear()
        console.session_history.clear()
        return "Session history and context cleared."


async def _handle_quit(console: AuraCodeConsole, args: str) -> str | None:
    """Exit the REPL."""
    console.running = False
    return None


async def _handle_prefs(console: AuraCodeConsole, args: str) -> str | None:
    """View or set persistent preferences."""
    if not hasattr(console, "preferences_manager") or console.preferences_manager is None:
        return "Preferences manager not available."

    mgr = console.preferences_manager
    parts = args.strip().split(maxsplit=2)
    subcmd = parts[0].lower() if parts else ""

    if subcmd == "set":
        if len(parts) < 3:
            return "Usage: /prefs set <key> <value>"
        key, value = parts[1], parts[2]
        try:
            mgr.set(key, value)
            return f"Set {key} = {mgr.get(key)}"
        except AttributeError as exc:
            return str(exc)
        except (ValueError, TypeError) as exc:
            return f"Invalid value: {exc}"

    if subcmd == "reset":
        from auracode.models.preferences import UserPreferences

        # Reset to defaults
        data = UserPreferences().model_dump()
        for k, v in data.items():
            mgr.set(k, v)
        return "Preferences reset to defaults."

    # Default: show all preferences
    prefs = mgr.preferences
    lines = ["", "User Preferences:"]
    for key, value in prefs.model_dump().items():
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("Set with: /prefs set <key> <value>")
    lines.append("Reset with: /prefs reset")
    return "\n".join(lines)


async def _handle_explain(console: AuraCodeConsole, args: str) -> str | None:
    """Explain a file (shortcut for 'explain <file>' prompt)."""
    path = args.strip()
    if not path:
        return "Usage: /explain <file>"
    return await console.send_prompt(f"explain {path}", intent_hint="explain")


async def _handle_review(console: AuraCodeConsole, args: str) -> str | None:
    """Review a file (shortcut for 'review <file>' prompt)."""
    path = args.strip()
    if not path:
        return "Usage: /review <file>"
    return await console.send_prompt(f"review {path}", intent_hint="review")


def register_builtin_commands() -> None:
    """Register all built-in slash commands."""
    _COMMANDS.clear()

    register(SlashCommand("help", "Show this help message", _handle_help, ["h", "?"]))
    register(SlashCommand("status", "Show engine health and session info", _handle_status))
    register(
        SlashCommand(
            "catalog",
            "List models, services, and analyzers",
            _handle_catalog,
            ["models"],
        )
    )
    register(SlashCommand("analyzer", "View or switch route analyzer", _handle_analyzer))
    register(SlashCommand("adapter", "Switch or list adapters", _handle_adapter))
    register(SlashCommand("claude", "Switch to Claude Code adapter", _handle_claude))
    register(SlashCommand("copilot", "Switch to Copilot adapter", _handle_copilot))
    register(SlashCommand("aider", "Switch to Aider adapter", _handle_aider))
    register(SlashCommand("codestral", "Switch to Codestral adapter", _handle_codestral))
    register(SlashCommand("context", "Add or list context files", _handle_context, ["ctx"]))
    register(SlashCommand("clear", "Clear history and/or context", _handle_clear))
    register(
        SlashCommand(
            "prefs",
            "View or set persistent preferences",
            _handle_prefs,
            ["preferences"],
        )
    )
    register(SlashCommand("explain", "Explain a file", _handle_explain))
    register(SlashCommand("review", "Review a file", _handle_review))
    register(SlashCommand("quit", "Exit AuraCode", _handle_quit, ["q", "exit"]))
