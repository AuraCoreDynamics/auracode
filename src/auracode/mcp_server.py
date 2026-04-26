"""Reverse-MCP server — exposes AuraCode capabilities as MCP tools."""

from __future__ import annotations

import uuid
from typing import Any


def create_mcp_server(engine: Any) -> Any | None:
    """Create an MCP server exposing AuraCode capabilities as tools.

    Returns ``None`` if the ``mcp`` package is not installed.
    """
    try:
        from mcp.server import FastMCP
    except ImportError:
        return None

    server = FastMCP("auracode")

    def _build_request(
        prompt: str,
        intent: str,
        adapter: str = "mcp",
        execution_mode: str = "standard",
        routing_preference: str = "auto",
        sovereignty_enforcement: str = "none",
        retrieval_mode: str = "disabled",
        context_session: Any = None,
    ):
        """Build an EngineRequest with typed execution policy."""
        from auracode.models.request import (
            EngineRequest,
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

        try:
            req_intent = RequestIntent(intent)
        except ValueError:
            req_intent = RequestIntent.GENERATE_CODE

        try:
            mode = ExecutionMode(execution_mode)
        except ValueError:
            mode = ExecutionMode.STANDARD

        try:
            routing = RoutingPreference(routing_preference)
        except ValueError:
            routing = RoutingPreference.AUTO

        try:
            sov = SovereigntyEnforcement(sovereignty_enforcement)
        except ValueError:
            sov = SovereigntyEnforcement.NONE

        try:
            ret = RetrievalMode(retrieval_mode)
        except ValueError:
            ret = RetrievalMode.DISABLED

        policy = ExecutionPolicy(
            mode=mode,
            routing=routing,
            sovereignty=SovereigntyPolicy(enforcement=sov),
            retrieval=RetrievalPolicy(mode=ret),
            latency=LatencyBudget(),
        )

        return EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=req_intent,
            prompt=prompt,
            adapter_name=adapter,
            execution_policy=policy,
            context=context_session,
        )

    @server.tool()
    async def auracode_generate(
        prompt: str,
        intent: str = "generate_code",
        execution_mode: str = "standard",
        routing_preference: str = "auto",
    ) -> str:
        """Generate code using AuraCode's engine."""
        req = _build_request(
            prompt,
            intent,
            execution_mode=execution_mode,
            routing_preference=routing_preference,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_plan(
        prompt: str,
        execution_mode: str = "standard",
    ) -> str:
        """Plan an architecture or implementation approach."""
        req = _build_request(prompt, "plan", execution_mode=execution_mode)
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_refactor(
        prompt: str,
        execution_mode: str = "standard",
    ) -> str:
        """Refactor code according to the given instructions."""
        req = _build_request(prompt, "refactor", execution_mode=execution_mode)
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_review_diff(
        prompt: str,
        sovereignty_enforcement: str = "none",
    ) -> str:
        """Review a code diff for correctness and security."""
        req = _build_request(
            prompt,
            "review_diff",
            sovereignty_enforcement=sovereignty_enforcement,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_security_review(
        prompt: str,
        sovereignty_enforcement: str = "warn",
    ) -> str:
        """Security-focused code review."""
        req = _build_request(
            prompt,
            "security_review",
            sovereignty_enforcement=sovereignty_enforcement,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_trace() -> str:
        """Return the last execution trace metadata."""
        # The engine doesn't store last response globally, so return
        # what the MCP server can observe.
        return "Use /trace in the REPL for execution trace. MCP trace support pending."

    @server.tool()
    async def auracode_explain(file_path: str) -> str:
        """Explain a file's contents."""
        from pathlib import Path

        from auracode.models.context import FileContext, SessionContext

        content: str | None = None
        p = Path(file_path)
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = None

        file_ctx = FileContext(
            path=str(p),
            content=content,
            language=p.suffix.lstrip(".") or None,
        )
        session = SessionContext(
            session_id=str(uuid.uuid4()),
            working_directory=str(p.parent),
            files=[file_ctx],
        )
        req = _build_request(
            f"Explain the contents of {file_path}",
            "explain_code",
            context_session=session,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_review(file_path: str) -> str:
        """Review code in a file."""
        from pathlib import Path

        from auracode.models.context import FileContext, SessionContext

        content: str | None = None
        p = Path(file_path)
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                content = None

        file_ctx = FileContext(
            path=str(p),
            content=content,
            language=p.suffix.lstrip(".") or None,
        )
        session = SessionContext(
            session_id=str(uuid.uuid4()),
            working_directory=str(p.parent),
            files=[file_ctx],
        )
        req = _build_request(
            f"Review the code in {file_path}",
            "review",
            context_session=session,
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_models() -> str:
        """List available models."""
        models = await engine.router.list_models()
        if not models:
            return "No models available"
        return "\n".join(f"{m.model_id} ({m.provider})" for m in models)

    from pathlib import Path

    def _safe_resolve(file_path: str, working_dir: str) -> Path | None:
        """Resolve *file_path* and verify it lives under *working_dir*.

        Returns the resolved ``Path`` on success, or ``None`` if the path
        escapes the working directory (path-traversal protection).
        """
        base = Path(working_dir).resolve()
        target = (base / file_path).resolve()
        is_same = str(target) == str(base)
        is_under = str(target).startswith(str(base) + "\\") or str(target).startswith(
            str(base) + "/"
        )
        if not (is_same or is_under):
            return None
        return target

    @server.tool()
    async def auracode_read_file(path: str) -> str:
        """Read a file from the local filesystem."""
        working_dir = getattr(engine.config, "working_directory", ".")
        resolved = _safe_resolve(path, working_dir)
        if resolved is None:
            return f"Error: Path '{path}' is outside the working directory."

        if not resolved.is_file():
            return f"Error: {path} is not a file or does not exist."

        try:
            return resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return f"Error reading file: {e}"

    @server.tool()
    async def auracode_write_file(path: str, content: str) -> str:
        """Write a file to the local filesystem. Requires allow_file_write permission."""
        from auracode.utils.journal import FileJournal

        if not engine.config.permissions.allow_file_write:
            return "Error: File write permission denied. Restart with --allow-write."

        working_dir = getattr(engine.config, "working_directory", ".")
        resolved = _safe_resolve(path, working_dir)
        if resolved is None:
            return f"Error: Path '{path}' is outside the working directory."

        before_content = None
        if resolved.exists():
            before_content = resolved.read_text(encoding="utf-8", errors="replace")

        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")

            # Record in journal (Task 2.3)
            if not hasattr(engine, "_journal"):
                engine._journal = FileJournal()
            engine._journal.record(str(resolved), "write", before_content, content)

            return f"Successfully wrote to {resolved}"
        except Exception as e:
            return f"Error writing file: {e}"

    @server.tool()
    async def auracode_edit_file(path: str, old_text: str, new_text: str) -> str:
        """Edit a file by replacing old_text with new_text. Requires allow_file_write."""
        from auracode.utils.journal import FileJournal

        if not engine.config.permissions.allow_file_write:
            return "Error: File write permission denied. Restart with --allow-write."

        working_dir = getattr(engine.config, "working_directory", ".")
        resolved = _safe_resolve(path, working_dir)
        if resolved is None:
            return f"Error: Path '{path}' is outside the working directory."

        if not resolved.is_file():
            return f"Error: {path} is not a file."

        content = resolved.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            return f"Error: old_text not found in {path}"

        new_content = content.replace(old_text, new_text)
        try:
            resolved.write_text(new_content, encoding="utf-8")

            # Record in journal (Task 2.3)
            if not hasattr(engine, "_journal"):
                engine._journal = FileJournal()
            engine._journal.record(
                str(resolved),
                "edit",
                content,
                new_content,
                {"old_text": old_text, "new_text": new_text},
            )

            return f"Successfully edited {resolved}"
        except Exception as e:
            return f"Error editing file: {e}"

    @server.tool()
    async def auracode_bash(command: str) -> str:
        """Execute a shell command. Requires allow_shell_commands."""
        import shlex
        import subprocess
        import sys

        if not engine.config.permissions.allow_shell_commands:
            return "Error: Shell command permission denied. Restart with --allow-shell."

        if not engine.config.permissions.allow_destructive_shell_commands:
            import re

            destructive_patterns = [
                r"rm\s",
                r"mv\s",
                r"git\s+reset",
                r"git\s+clean",
                r"powershell",
                r"pwsh",
                r"del\s",
                r"rmdir\s",
                r"rd\s",
                r"format\s",
            ]
            if any(re.search(p, command) for p in destructive_patterns):
                return "Error: Destructive command blocked. Restart with --unsafe to allow."

        try:
            if sys.platform == "win32":
                # Windows: use cmd.exe explicitly instead of shell=True
                args = ["cmd.exe", "/c", command]
            else:
                # Unix: parse into argument list for safe execution
                args = shlex.split(command)
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=60,
            )
            return (
                f"Exit code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
            )
        except Exception as e:
            return f"Error executing command: {e}"

    return server
