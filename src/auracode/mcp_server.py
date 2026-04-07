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

    @server.tool()
    async def auracode_write_file(path: str, content: str) -> str:
        """Write a file to the local filesystem. Requires allow_file_write permission."""
        from pathlib import Path

        from auracode.utils.journal import FileJournal

        if not engine.config.permissions.allow_file_write:
            return "Error: File write permission denied. Restart with --allow-write."

        p = Path(path)
        before_content = None
        if p.exists():
            before_content = p.read_text(encoding="utf-8", errors="replace")

        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

            # Record in journal (Task 2.3)
            if not hasattr(engine, "_journal"):
                engine._journal = FileJournal()
            engine._journal.record(path, "write", before_content, content)

            return f"Successfully wrote to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    @server.tool()
    async def auracode_edit_file(path: str, old_text: str, new_text: str) -> str:
        """Edit a file by replacing old_text with new_text. Requires allow_file_write."""
        from pathlib import Path

        from auracode.utils.journal import FileJournal

        if not engine.config.permissions.allow_file_write:
            return "Error: File write permission denied. Restart with --allow-write."

        p = Path(path)
        if not p.is_file():
            return f"Error: {path} is not a file."

        content = p.read_text(encoding="utf-8", errors="replace")
        if old_text not in content:
            return f"Error: old_text not found in {path}"

        new_content = content.replace(old_text, new_text)
        try:
            p.write_text(new_content, encoding="utf-8")

            # Record in journal (Task 2.3)
            if not hasattr(engine, "_journal"):
                engine._journal = FileJournal()
            engine._journal.record(
                path, "edit", content, new_content, {"old_text": old_text, "new_text": new_text}
            )

            return f"Successfully edited {path}"
        except Exception as e:
            return f"Error editing file: {e}"

    @server.tool()
    async def auracode_bash(command: str) -> str:
        """Execute a bash command. Requires allow_shell_commands."""
        import re
        import subprocess

        if not engine.config.permissions.allow_shell_commands:
            return "Error: Shell command permission denied. Restart with --allow-shell."

        if not engine.config.permissions.allow_destructive_shell_commands:
            destructive_patterns = [r"rm\s", r"mv\s", r"git\s+reset", r"git\s+clean"]
            if any(re.search(p, command) for p in destructive_patterns):
                return "Error: Destructive command blocked. Restart with --unsafe to allow."

        try:
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
            return (
                f"Exit code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}"
            )
        except Exception as e:
            return f"Error executing command: {e}"

    return server
