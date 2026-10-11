"""Slash-command registry for the interactive REPL."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from auracode.repl.console import AuraCodeConsole

logger = logging.getLogger("AuraCode.REPL")


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
    exec_mode = getattr(console, "_execution_mode", "standard")
    sov_mode = getattr(console, "_sovereignty_enforcement", "none")
    ret_mode = getattr(console, "_retrieval_mode", "disabled")
    lines = [
        "",
        "AuraCode Status",
        f"  Active adapter:  {adapter_name}",
        f"  Active analyzer: {analyzer_name}",
        f"  Execution mode:  {exec_mode}",
        f"  Sovereignty:     {sov_mode}",
        f"  Retrieval:       {ret_mode}",
        f"  Router:          {'healthy' if healthy else 'unavailable'}",
        f"  Catalog:         {len(models)} models, "
        f"{len(services)} services, {len(analyzers)} analyzers",
        f"  Session history: {len(console.session_history)} messages",
    ]

    xlm_ep = getattr(console.engine.config, "auraxlm_endpoint", None)
    if xlm_ep:
        lines.append(f"  Retrieval:       AuraXLM neural ({xlm_ep})")
    else:
        lines.append("  Retrieval:       Local deterministic AST repo-map (zero-vector)")

    # Show active degradations if any.
    last_meta = getattr(console, "_last_execution_metadata", None)
    if last_meta and last_meta.degradations:
        lines.append(f"  Active degradations: {len(last_meta.degradations)}")

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
            except Exception as ex:  # noqa: F841
                logger.debug("repl.commands._handle_analyzer_error", exc_info=True)
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
        except Exception as ex:  # noqa: F841
            logger.debug("repl.commands._handle_adapter_error", exc_info=True)
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


# ── FMoE control commands (TG5) ──────────────────────────────────────


async def _handle_mode(console: AuraCodeConsole, args: str) -> str | None:
    """View or set the execution mode."""
    from auracode.models.request import ExecutionMode

    name = args.strip().lower()
    if not name:
        current = getattr(console, "_execution_mode", "standard")
        modes = [m.value for m in ExecutionMode]
        lines = [f"Execution mode: {current}", f"Available: {', '.join(modes)}"]
        return "\n".join(lines)

    try:
        mode = ExecutionMode(name)
    except ValueError:
        return f"Unknown mode '{name}'. Available: standard, speculative, monologue"

    console._execution_mode = mode.value
    if hasattr(console, "preferences_manager") and console.preferences_manager:
        try:
            console.preferences_manager.set("default_execution_mode", mode.value)
        except (AttributeError, Exception):
            pass
    return f"Execution mode: {mode.value}"


async def _handle_sovereignty(console: AuraCodeConsole, args: str) -> str | None:
    """View or set sovereignty posture."""
    from auracode.models.request import SovereigntyEnforcement

    name = args.strip().lower()
    if not name:
        current = getattr(console, "_sovereignty_enforcement", "none")
        label = getattr(console, "_sensitivity_label", None)
        lines = [f"Sovereignty: {current}"]
        if label:
            lines.append(f"Sensitivity label: {label}")
        return "\n".join(lines)

    try:
        enforcement = SovereigntyEnforcement(name)
    except ValueError:
        return f"Unknown enforcement '{name}'. Available: none, warn, enforce"

    console._sovereignty_enforcement = enforcement.value
    return f"Sovereignty: {enforcement.value}"


async def _handle_retrieval(console: AuraCodeConsole, args: str) -> str | None:
    """View or set retrieval mode."""
    from auracode.models.request import RetrievalMode

    name = args.strip().lower()
    if not name:
        current = getattr(console, "_retrieval_mode", "disabled")
        return f"Retrieval mode: {current}"

    try:
        mode = RetrievalMode(name)
    except ValueError:
        return f"Unknown retrieval mode '{name}'. Available: disabled, auto, required"

    console._retrieval_mode = mode.value
    return f"Retrieval mode: {mode.value}"


async def _handle_trace(console: AuraCodeConsole, args: str) -> str | None:
    """Show the last execution trace/metadata."""
    last_meta = getattr(console, "_last_execution_metadata", None)
    if last_meta is None:
        return "No execution trace available. Send a prompt first."

    lines = ["Last execution trace:"]
    if last_meta.analyzer_used:
        lines.append(f"  Analyzer: {last_meta.analyzer_used}")
    if last_meta.execution_mode_used:
        lines.append(f"  Mode used: {last_meta.execution_mode_used}")
    if last_meta.sovereignty_outcome:
        lines.append(f"  Sovereignty: {last_meta.sovereignty_outcome}")
    if last_meta.retrieval_summary:
        lines.append(f"  Retrieval: {last_meta.retrieval_summary}")
    if last_meta.trace_id:
        lines.append(f"  Trace ID: {last_meta.trace_id}")
    if last_meta.verification_outcome:
        lines.append(f"  Verification: {last_meta.verification_outcome}")
    if last_meta.degradations:
        lines.append(f"  Degradations ({len(last_meta.degradations)}):")
        for d in last_meta.degradations:
            lines.append(f"    {d.capability}: {d.requested} -> {d.actual} ({d.reason})")
    if last_meta.backend_warnings:
        lines.append(f"  Warnings: {'; '.join(last_meta.backend_warnings)}")
    if len(lines) == 1:
        lines.append("  (no metadata captured)")
    return "\n".join(lines)


async def _handle_capabilities(console: AuraCodeConsole, args: str) -> str | None:
    """Show backend capabilities."""
    try:
        caps = await console.engine.router.get_capabilities()
    except Exception as ex:  # noqa: F841
        logger.debug("repl.commands._handle_capabilities_error", exc_info=True)
        return "Unable to query backend capabilities."

    if not caps:
        return "No capability data available from backend."

    lines = ["Backend capabilities:"]
    for c in caps:
        status = "supported" if c.supported else "not supported"
        desc = f" — {c.description}" if c.description else ""
        lines.append(f"  {c.capability_id}: {status}{desc}")
    return "\n".join(lines)


async def _handle_spend(console: AuraCodeConsole, args: str) -> str | None:
    """Show current budget spend and limits."""
    status = await console.engine.get_budget_status()
    if "error" in status:
        return f"Error retrieving budget: {status['error']}"

    lines = ["", "Agentic Spend / Budget Status:"]
    enabled = "Enabled" if status.get("enabled") else "Disabled"
    lines.append(f"  Status: {enabled}")

    daily_spend = status.get("daily_spend", 0.0)
    daily_limit = status.get("daily_limit")
    limit_str = f" / ${daily_limit:.2f}" if daily_limit is not None else ""
    lines.append(f"  Daily: ${daily_spend:.2f}{limit_str}")

    monthly_spend = status.get("monthly_spend", 0.0)
    monthly_limit = status.get("monthly_limit")
    mlimit_str = f" / ${monthly_limit:.2f}" if monthly_limit is not None else ""
    lines.append(f"  Monthly: ${monthly_spend:.2f}{mlimit_str}")

    return "\n".join(lines)


async def _handle_permissions(console: AuraCodeConsole, args: str) -> str | None:
    """View or set local execution permissions."""
    parts = args.strip().split()
    if not parts:
        perms = console.engine.config.permissions
        lines = ["", "Local Agent Permissions:"]
        lines.append(f"  allow_file_write: {perms.allow_file_write}")
        lines.append(f"  allow_shell_commands: {perms.allow_shell_commands}")
        lines.append(
            f"  allow_destructive_shell_commands (unsafe): {perms.allow_destructive_shell_commands}"
        )
        lines.append("")
        lines.append("Toggle with: /permissions <name> <on|off>")
        return "\n".join(lines)

    if len(parts) < 2:
        return "Usage: /permissions <name> <on|off>"

    name, val = parts[0], parts[1].lower()
    enabled = val in ("on", "true", "yes")

    if hasattr(console.engine.config.permissions, name):
        setattr(console.engine.config.permissions, name, enabled)
        return f"Permission '{name}' set to {enabled}."
    else:
        return f"Unknown permission: {name}"


async def _handle_act(console: AuraCodeConsole, args: str) -> str | None:
    """Run an autonomous self-healing agent loop with verification."""
    import uuid

    from auracode.models.request import EngineRequest, RequestIntent
    from auracode.models.verification import VerificationCommand

    if not args.strip():
        return 'Usage: /act PROMPT [--verify "CMD"]'

    prompt = args.strip()
    verif_cmd: str | None = None
    if "--verify" in args:
        parts = args.split("--verify", 1)
        prompt = parts[0].strip()
        verif_cmd = parts[1].strip().strip('"').strip("'")

    verif = (
        VerificationCommand(
            command=verif_cmd,
            working_directory=console.session.working_directory,
        )
        if verif_cmd
        else None
    )

    req = EngineRequest(
        request_id=str(uuid.uuid4()),
        intent=RequestIntent.GENERATE_CODE,
        prompt=prompt,
        context=console.session,
        adapter_name=console.active_adapter.name if console.active_adapter else "opencode",
    )

    result = await console.engine.execute_loop(req, verification=verif)
    lines = [f"[Agent Loop Status: {result.status}]"]
    if result.remediations:
        lines.append(f"Remediation steps ({len(result.remediations)} attempts):")
        for step in result.remediations:
            status_tag = "PASS" if step.verification.passed else "FAIL"
            lines.append(
                f"  Attempt {step.attempt}: {status_tag} "
                f"(exit {step.verification.exit_code}, {step.verification.duration_ms}ms)"
            )
    if result.rollback_available and result.snapshot_id:
        lines.append(f"Snapshot created: {result.snapshot_id} (revert with /rollback)")
    if result.final_response and result.final_response.content:
        lines.append("")
        lines.append(result.final_response.content)

    return "\n".join(lines)


async def _handle_verify(console: AuraCodeConsole, args: str) -> str | None:
    """Manually run a verification command."""
    from auracode.engine.agent_loop import AgenticExecutionLoop
    from auracode.models.verification import VerificationCommand

    cmd = args.strip()
    if not cmd:
        return "Usage: /verify <command>"

    verif = VerificationCommand(
        command=cmd,
        working_directory=console.session.working_directory,
    )
    loop = AgenticExecutionLoop(console.engine)
    res = await loop._run_verification(verif)

    status_tag = "PASSED" if res.passed else "FAILED"
    lines = [
        f"Verification {status_tag} (exit code: {res.exit_code}, {res.duration_ms}ms)",
        f"Command: {res.command}",
    ]
    if res.stdout:
        lines.append(f"STDOUT:\n{res.stdout.strip()}")
    if res.stderr:
        lines.append(f"STDERR:\n{res.stderr.strip()}")
    return "\n".join(lines)


async def _handle_rollback(console: AuraCodeConsole, args: str) -> str | None:
    """Roll back file changes to a previous snapshot."""
    journal = getattr(console.engine, "_journal", None)
    if not journal or not journal.snapshots:
        return "No active rollback snapshots available."

    snap_id = args.strip()
    if not snap_id:
        # Pick the most recent snapshot
        snap_id = list(journal.snapshots.keys())[-1]

    try:
        paths = journal.rollback_snapshot(snap_id)
        if not paths:
            return f"Snapshot {snap_id} rolled back. (No files modified)."
        restored_list = "\n".join(f"  - {p}" for p in paths)
        return f"Snapshot {snap_id} successfully rolled back. Restored files:\n{restored_list}"
    except KeyError:
        return f"Snapshot ID '{snap_id}' not found."


async def _handle_repomap(console: AuraCodeConsole, args: str) -> str | None:
    """Show the structural AST repo-map for the current workspace."""
    from auracode.engine.repo_map import RepoMapBuilder

    work_dir = console.session.working_directory if console.session else "."
    builder = RepoMapBuilder(work_dir)
    map_text = builder.build()
    file_count, symbol_count = builder.count_symbols()
    summary = f"Discovered {symbol_count} symbols across {file_count} files in {work_dir}\n\n"
    return summary + map_text


async def _handle_conflicts(console: AuraCodeConsole, args: str) -> str | None:
    """List files in the current workspace with active Git conflict markers."""
    from pathlib import Path

    from auracode.git.conflict_resolver import ConflictMarkerParser

    work_dir = console.session.working_directory if console.session else "."
    conflicted = ConflictMarkerParser.find_conflicted_files(work_dir)
    if not conflicted:
        return "No active Git merge conflicts detected."

    lines = [f"Found {len(conflicted)} conflicted file(s):"]
    root_p = Path(work_dir).resolve()
    for p in conflicted:
        lines.append(f"  - {p.relative_to(root_p).as_posix()}")
    lines.append("\nResolve with: /resolve-conflicts [file]")
    return "\n".join(lines)


async def _handle_resolve_conflicts(console: AuraCodeConsole, args: str) -> str | None:
    """Resolve merge conflicts using AI synthesis."""
    from pathlib import Path

    from auracode.git.conflict_resolver import (
        ConflictMarkerParser,
        MergeConflictResolver,
    )

    work_dir = console.session.working_directory if console.session else "."
    resolver = MergeConflictResolver(console.engine)

    target = args.strip()
    if target:
        target_path = Path(work_dir) / target
        _success, msg = await resolver.resolve_file(target_path)
        return msg

    conflicted = ConflictMarkerParser.find_conflicted_files(work_dir)
    if not conflicted:
        return "No active Git merge conflicts detected."

    results: list[str] = []
    for p in conflicted:
        success, msg = await resolver.resolve_file(p)
        tag = "RESOLVED" if success else "FAILED"
        results.append(f"[{tag}] {p.name}: {msg}")
    return "\n".join(results)


async def _handle_commit(console: AuraCodeConsole, args: str) -> str | None:
    """Synthesize conventional commit message and commit staged changes."""
    from auracode.git.commit_synthesizer import CommitSynthesizer

    work_dir = console.session.working_directory if console.session else "."
    synthesizer = CommitSynthesizer(console.engine)
    push = "--push" in args.split()
    custom_msg = args.replace("--push", "").strip() or None

    _success, output = await synthesizer.commit_staged(
        repo_path=work_dir,
        message=custom_msg,
        push=push,
    )
    status_tag = "SUCCESS" if _success else "FAILED"
    return f"[Commit {status_tag}]\n{output}"


async def _handle_bundle(console: AuraCodeConsole, args: str) -> str | None:
    """Manage AuraGrid application bundles (.aurabundle)."""
    from pathlib import Path

    from auracode.bundle.manifest import ManifestValidator
    from auracode.bundle.packager import BundlePackager

    parts = args.strip().split()
    subcmd = parts[0] if parts else "help"

    if subcmd == "pack":
        src = (
            parts[1]
            if len(parts) > 1
            else (console.session.working_directory if console.session else ".")
        )
        out = parts[2] if len(parts) > 2 else f"{Path(src).resolve().name}.aurabundle"
        try:
            packed = BundlePackager.pack(src, out)
            return f"Bundle created: {packed}"
        except Exception as exc:
            return f"Bundle pack failed: {exc}"

    if subcmd == "validate":
        target = parts[1] if len(parts) > 1 else "app.manifest.json"
        p = Path(target).resolve()
        if p.suffix in (".aurabundle", ".zip"):
            try:
                info = BundlePackager.inspect(p)
                return f"Bundle valid: {info['name']} v{info['version']} ({info['sha256'][:16]}...)"
            except Exception as exc:
                return f"Bundle invalid: {exc}"
        else:
            is_valid, errors = ManifestValidator.validate_file(p)
            if is_valid:
                return f"Manifest valid: {p.name}"
            return "Manifest errors:\n" + "\n".join(f"  - {e}" for e in errors)

    if subcmd == "inspect":
        target = parts[1] if len(parts) > 1 else "auracode.aurabundle"
        try:
            info = BundlePackager.inspect(target)
            return (
                f"Bundle: {info['name']} v{info['version']} ({info['app_id']})\n"
                f"SHA256: {info['sha256']}\n"
                f"Files ({info['file_count']}):\n  " + "\n  ".join(info["files"][:10])
            )
        except Exception as exc:
            return f"Inspect failed: {exc}"

    return "Usage: /bundle [pack [src] [out] | validate [target] | inspect [bundle]]"


async def _handle_mas_status(console: AuraCodeConsole, args: str) -> str | None:
    """Show node-local MAS registration status and advertised MCP tools."""
    from auracode.grid.mas_agent import DEFAULT_MAS_ENDPOINT

    mas_ep = getattr(console.engine.config, "mas_endpoint", None) or DEFAULT_MAS_ENDPOINT
    tools = [
        "auracode_act",
        "auracode_repomap",
        "auracode_conflicts",
        "auracode_resolve_conflicts",
        "auracode_rollback",
        "auracode_synthesize_commit",
        "auracode_bundle_pack",
        "auracode_bundle_validate",
    ]
    lines = [
        "",
        "Node-Local Multi-Agent System (MAS) Status",
        f"  MAS Endpoint:     {mas_ep}",
        "  Role:             code-engine",
        "  Advertised MCP Tools:",
    ]
    for t in tools:
        lines.append(f"    - {t}")
    lines.append("")
    lines.append("MAS integration is ready for grid prototype-generation and governance.")
    return "\n".join(lines)


async def _handle_grid_mirror(console: AuraCodeConsole, args: str) -> str | None:
    """Manage distributed bare Git mirrors on AuraGrid cluster storage."""
    from pathlib import Path

    from auracode.git.grid_mirror import GridMirrorOrchestrator

    parts = args.strip().split()
    subcmd = parts[0] if parts else "status"

    default_storage = getattr(console.engine.config, "grid_storage_mirrors_path", None) or str(
        Path.home() / ".auracode" / "grid_mirrors"
    )

    if subcmd == "init":
        app_id = parts[1] if len(parts) > 1 else "auracode"
        storage = parts[2] if len(parts) > 2 else default_storage
        try:
            m_path = GridMirrorOrchestrator.init_grid_mirror(app_id, storage)
            return f"Initialized shared grid mirror: {m_path}"
        except Exception as exc:
            return f"Failed to init grid mirror: {exc}"

    if subcmd == "sync":
        if len(parts) < 3:
            return "Usage: /grid-mirror sync <mirror_path> <local_target>"
        mirror_p = parts[1]
        local_t = parts[2]
        try:
            ok = GridMirrorOrchestrator.sync_mirror_to_node(mirror_p, local_t)
            return f"Sync {'succeeded' if ok else 'failed'} from {mirror_p} to {local_t}"
        except Exception as exc:
            return f"Sync error: {exc}"

    if subcmd == "status":
        mirror_p = parts[1] if len(parts) > 1 else str(Path(default_storage) / "auracode.git")
        info = GridMirrorOrchestrator.get_mirror_info(mirror_p)
        if not info.get("exists"):
            return f"Grid mirror not found at {mirror_p}"
        return (
            f"Grid Mirror: {info['path']}\n"
            f"  HEAD Ref:       {info['head_ref']}\n"
            f"  Latest Commit:  {info['latest_commit']}"
        )

    return (
        "Usage: /grid-mirror [init <app_id> [storage_path] | "
        "sync <mirror> <target> | status [mirror]]"
    )


async def _handle_xlm_benchmark(console: AuraCodeConsole, args: str) -> str | None:
    """Benchmark AuraXLM neural retrieval endpoint connectivity and latency."""
    import time

    import httpx

    xlm_ep = getattr(console.engine.config, "auraxlm_endpoint", None)
    if not xlm_ep:
        return (
            "AuraXLM endpoint not configured.\n"
            "Connect AuraXLM on AuraGrid to enable neural vector search and cross-encoder "
            "semantic indexing.\n"
            "Set 'auraxlm_endpoint' in auracode.yaml or config."
        )

    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{xlm_ep.rstrip('/')}/health")
        latency_ms = int((time.time() - t0) * 1000)
        status = "HEALTHY" if resp.is_success else f"HTTP {resp.status_code}"
        return (
            f"AuraXLM Benchmark Report\n"
            f"  Endpoint: {xlm_ep}\n"
            f"  Status:   {status}\n"
            f"  Latency:  {latency_ms}ms\n"
            f"  Mode:     Distributed Neural Vector Indexing"
        )
    except Exception as exc:
        latency_ms = int((time.time() - t0) * 1000)
        return (
            f"AuraXLM Benchmark Report\n"
            f"  Endpoint: {xlm_ep}\n"
            f"  Status:   UNREACHABLE ({exc})\n"
            f"  Latency:  {latency_ms}ms"
        )


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
    register(SlashCommand("mode", "View or set execution mode", _handle_mode))
    register(
        SlashCommand("sovereignty", "View or set sovereignty posture", _handle_sovereignty, ["sov"])
    )
    register(SlashCommand("retrieval", "View or set retrieval mode", _handle_retrieval, ["rag"]))
    register(SlashCommand("trace", "Show last execution trace", _handle_trace))
    register(
        SlashCommand("capabilities", "Show backend capabilities", _handle_capabilities, ["caps"])
    )
    register(SlashCommand("spend", "Show agentic spend and budget limits", _handle_spend))
    register(
        SlashCommand("permissions", "View or set local permissions", _handle_permissions, ["perms"])
    )
    register(
        SlashCommand(
            "act",
            "Run autonomous self-healing agent loop",
            _handle_act,
            ["agent"],
        )
    )
    register(
        SlashCommand(
            "verify",
            "Run verification test or build command",
            _handle_verify,
        )
    )
    register(
        SlashCommand(
            "rollback",
            "Revert files to previous snapshot",
            _handle_rollback,
            ["undo"],
        )
    )
    register(
        SlashCommand(
            "repomap",
            "Show structural AST repo-map",
            _handle_repomap,
            ["map"],
        )
    )
    register(
        SlashCommand(
            "conflicts",
            "List files with active merge conflicts",
            _handle_conflicts,
        )
    )
    register(
        SlashCommand(
            "resolve-conflicts",
            "Resolve 3-way merge conflicts using AI",
            _handle_resolve_conflicts,
            ["resolve"],
        )
    )
    register(
        SlashCommand(
            "commit",
            "Synthesize conventional commit and commit staged",
            _handle_commit,
        )
    )
    register(
        SlashCommand(
            "bundle",
            "Manage AuraGrid application bundles",
            _handle_bundle,
        )
    )
    register(
        SlashCommand(
            "mas-status",
            "Show node-local MAS status and MCP tools",
            _handle_mas_status,
            ["mas"],
        )
    )
    register(
        SlashCommand(
            "grid-mirror",
            "Manage distributed Git bare mirrors",
            _handle_grid_mirror,
        )
    )
    register(
        SlashCommand(
            "xlm-benchmark",
            "Benchmark AuraXLM retrieval latency",
            _handle_xlm_benchmark,
        )
    )
    register(SlashCommand("quit", "Exit AuraCode", _handle_quit, ["q", "exit"]))
