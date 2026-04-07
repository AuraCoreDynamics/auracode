"""Interactive REPL console for AuraCode."""

from __future__ import annotations

import asyncio
import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.theme import Theme

from auracode.adapters.base import BaseAdapter
from auracode.engine.core import AuraCodeEngine
from auracode.engine.preferences import PreferencesManager
from auracode.engine.registry import AdapterRegistry
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import (
    EngineRequest,
    EngineResponse,
    ExecutionMode,
    ExecutionPolicy,
    LatencyBudget,
    RequestIntent,
    RetrievalMode,
    RetrievalPolicy,
    RoutingPreference,
    SovereigntyEnforcement,
    SovereigntyPolicy,
)

# Intent keywords that appear at the start of a prompt.
_INTENT_PREFIXES: dict[str, RequestIntent] = {
    "explain": RequestIntent.EXPLAIN_CODE,
    "review": RequestIntent.REVIEW,
    "plan": RequestIntent.PLAN,
    "edit": RequestIntent.EDIT_CODE,
    "generate": RequestIntent.GENERATE_CODE,
    "write": RequestIntent.GENERATE_CODE,
    "create": RequestIntent.GENERATE_CODE,
    "implement": RequestIntent.GENERATE_CODE,
    "complete": RequestIntent.COMPLETE_CODE,
    "refactor": RequestIntent.REFACTOR,
    "security": RequestIntent.SECURITY_REVIEW,
    "test": RequestIntent.GENERATE_TESTS,
    "trace": RequestIntent.ARCHITECTURE_TRACE,
}

_THEME = Theme(
    {
        "prompt": "bold cyan",
        "adapter": "bold green",
        "info": "dim",
        "error": "bold red",
    }
)


class AuraCodeConsole:
    """Interactive REPL that routes prompts through adapters and the engine.

    Usage::

        console = AuraCodeConsole(engine, adapter_registry)
        asyncio.run(console.run())
    """

    def __init__(
        self,
        engine: AuraCodeEngine,
        adapter_registry: AdapterRegistry,
        *,
        default_adapter_name: str = "opencode",
        preferences_manager: PreferencesManager | None = None,
    ) -> None:
        self.engine = engine
        self.adapter_registry = adapter_registry
        self.active_adapter: BaseAdapter | None = adapter_registry.get(default_adapter_name)
        self.context_files: list[FileContext] = []
        self.session_history: list[dict[str, str]] = []
        self.session_id: str = uuid.uuid4().hex
        self.running: bool = False
        self.rich = Console(theme=_THEME)
        self.preferences_manager: PreferencesManager | None = preferences_manager
        self._active_analyzer_id: str | None = None

        # Register slash commands.
        from auracode.repl.commands import register_builtin_commands

        register_builtin_commands()

    # ── Prompt handling ────────────────────────────────────────────────

    def _detect_intent(self, text: str) -> RequestIntent:
        """Detect intent from the first word of the prompt."""
        first_word = text.strip().split(maxsplit=1)[0].lower() if text.strip() else ""
        return _INTENT_PREFIXES.get(first_word, RequestIntent.CHAT)

    def _build_session_context(self) -> SessionContext | None:
        """Build a SessionContext from current state."""
        if not self.context_files and not self.session_history:
            return None
        return SessionContext(
            session_id=self.session_id,
            working_directory=".",
            files=list(self.context_files),
            history=list(self.session_history),
        )

    async def send_prompt(self, text: str, *, intent_hint: str | None = None) -> str | None:
        """Send a prompt through the active adapter and engine, return formatted output."""
        if self.active_adapter is None:
            return "No adapter active. Use /adapter <name> to select one."

        # Determine intent.
        if intent_hint:
            intent_map = {
                "explain": RequestIntent.EXPLAIN_CODE,
                "review": RequestIntent.REVIEW,
                "plan": RequestIntent.PLAN,
                "edit": RequestIntent.EDIT_CODE,
                "generate": RequestIntent.GENERATE_CODE,
                "chat": RequestIntent.CHAT,
            }
            intent = intent_map.get(intent_hint, self._detect_intent(text))
        else:
            intent = self._detect_intent(text)

        context = self._build_session_context()

        # Build execution policy from session state (precedence: session > prefs > config defaults).
        exec_mode = getattr(self, "_execution_mode", "standard")
        sov_enforcement = getattr(self, "_sovereignty_enforcement", "none")
        sens_label = getattr(self, "_sensitivity_label", None)
        ret_mode = getattr(self, "_retrieval_mode", "disabled")
        routing_pref = getattr(self, "_routing_preference", "auto")

        try:
            mode = ExecutionMode(exec_mode)
        except ValueError:
            mode = ExecutionMode.STANDARD
        try:
            routing = RoutingPreference(routing_pref)
        except ValueError:
            routing = RoutingPreference.AUTO
        try:
            sov = SovereigntyEnforcement(sov_enforcement)
        except ValueError:
            sov = SovereigntyEnforcement.NONE
        try:
            ret = RetrievalMode(ret_mode)
        except ValueError:
            ret = RetrievalMode.DISABLED

        policy = ExecutionPolicy(
            mode=mode,
            routing=routing,
            sovereignty=SovereigntyPolicy(
                enforcement=sov,
                sensitivity_label=sens_label,
            ),
            retrieval=RetrievalPolicy(mode=ret),
            latency=LatencyBudget(),
        )

        request = EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=intent,
            prompt=text,
            context=context,
            adapter_name=self.active_adapter.name,
            execution_policy=policy,
        )

        response: EngineResponse = await self.engine.execute(request)

        # Stash execution metadata for /trace command.
        if response.execution_metadata is not None:
            self._last_execution_metadata = response.execution_metadata

        # Update session history.
        self.session_history.append({"role": "user", "content": text})
        self.session_history.append({"role": "assistant", "content": response.content})

        # Format through the adapter.
        formatted = await self.active_adapter.translate_response(response)
        return formatted

    # ── Slash command dispatch ─────────────────────────────────────────

    async def _dispatch_command(self, line: str) -> str | None:
        """Parse and dispatch a /command."""
        from auracode.repl.commands import get

        # Strip the leading /
        body = line[1:].strip()
        parts = body.split(maxsplit=1)
        cmd_name = parts[0].lower() if parts else ""
        cmd_args = parts[1] if len(parts) > 1 else ""

        cmd = get(cmd_name)
        if cmd is None:
            return f"Unknown command: /{cmd_name}. Type /help for available commands."

        return await cmd.handler(self, cmd_args)

    # ── Main loop ──────────────────────────────────────────────────────

    def _get_prompt_text(self) -> str:
        """Build the prompt string showing the active adapter and analyzer."""
        adapter_name = self.active_adapter.name if self.active_adapter else "auracode"
        # Show non-default analyzer in prompt
        analyzer_hint = ""
        if hasattr(self, "_active_analyzer_id") and self._active_analyzer_id:
            if self._active_analyzer_id != "aurarouter-default":
                analyzer_hint = f":{self._active_analyzer_id}"
        return f"{adapter_name}{analyzer_hint}> "

    def _print_banner(self) -> None:
        """Print the welcome banner."""
        from auracode import __version__

        banner_text = (
            f"[bold]AuraCode[/bold] v{__version__} — "
            f"terminal-native AI coding assistant\n\n"
            f"Type a prompt to get started. Use [bold cyan]/help[/bold cyan] for commands.\n"
            f"Switch adapters with [bold cyan]/claude[/bold cyan], "
            f"[bold cyan]/copilot[/bold cyan], [bold cyan]/aider[/bold cyan], "
            f"[bold cyan]/codestral[/bold cyan].\n"
            f"Press [bold]Ctrl+C[/bold] or type [bold cyan]/quit[/bold cyan] to exit."
        )
        self.rich.print(Panel(banner_text, border_style="cyan", padding=(1, 2)))

        if self.active_adapter:
            self.rich.print(f"[adapter]Active adapter: {self.active_adapter.name}[/adapter]\n")

    def _print_output(self, text: str) -> None:
        """Print a response, rendering markdown if rich is available."""
        try:
            self.rich.print(Markdown(text))
        except Exception:
            self.rich.print(text)

    async def run(self) -> None:
        """Run the interactive REPL loop."""
        self.running = True
        self._print_banner()

        while self.running:
            try:
                prompt_text = self._get_prompt_text()
                # Use rich prompt for color, fall back to input().
                try:
                    line = self.rich.input(f"[prompt]{prompt_text}[/prompt]")
                except EOFError:
                    break

                line = line.strip()
                if not line:
                    continue

                # Slash command.
                if line.startswith("/"):
                    result = await self._dispatch_command(line)
                    if result:
                        self.rich.print(result)
                    continue

                # Regular prompt — send through the engine.
                exec_mode = getattr(self, "_execution_mode", "standard")
                if exec_mode == "monologue":
                    # Streaming path for monologue
                    self.rich.print()
                    await self.stream_prompt(line)
                    self.rich.print()
                else:
                    result = await self.send_prompt(line)
                    if result:
                        self.rich.print()
                        self._print_output(result)
                        self.rich.print()

            except KeyboardInterrupt:
                self.rich.print("\n[info]Interrupted. Type /quit to exit.[/info]")
                continue
            except Exception as exc:
                self.rich.print(f"[error]Error: {exc}[/error]")
                continue

        self.rich.print("[info]Goodbye.[/info]")

    async def stream_prompt(self, text: str) -> None:
        """Send a prompt and stream the response to the console."""
        if self.active_adapter is None:
            self.rich.print("[error]No adapter active.[/error]")
            return

        intent = self._detect_intent(text)
        context = self._build_session_context()

        # Build execution policy
        exec_mode = getattr(self, "_execution_mode", "standard")
        sov_enforcement = getattr(self, "_sovereignty_enforcement", "none")
        routing_pref = getattr(self, "_routing_preference", "auto")

        policy = ExecutionPolicy(
            mode=ExecutionMode(exec_mode),
            routing=RoutingPreference(routing_pref),
            sovereignty=SovereigntyPolicy(enforcement=SovereigntyEnforcement(sov_enforcement)),
            retrieval=RetrievalPolicy(mode=RetrievalMode.DISABLED),
            latency=LatencyBudget(),
        )

        request = EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=intent,
            prompt=text,
            context=context,
            adapter_name=self.active_adapter.name,
            execution_policy=policy,
        )

        collected = []
        async for chunk in self.engine.execute_stream(request):
            # Task 3.3: render exploratory tool calls
            if chunk.startswith("[MONOLOGUE"):
                self.rich.print(f"[info]{chunk.strip()}[/info]")
            else:
                self.rich.print(chunk, end="")
                collected.append(chunk)

        full_content = "".join(collected)
        if full_content:
            self.session_history.append({"role": "user", "content": text})
            self.session_history.append({"role": "assistant", "content": full_content})

    def run_sync(self) -> None:
        """Synchronous wrapper for run()."""
        asyncio.run(self.run())
