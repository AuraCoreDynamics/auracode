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

    @server.tool()
    async def auracode_generate(
        prompt: str,
        intent: str = "generate_code",
        context_dir: str | None = None,
    ) -> str:
        """Generate code using AuraCode's engine."""
        from auracode.models.request import EngineRequest, RequestIntent

        # Map string intent to enum, default to GENERATE_CODE
        try:
            req_intent = RequestIntent(intent)
        except ValueError:
            req_intent = RequestIntent.GENERATE_CODE

        req = EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=req_intent,
            prompt=prompt,
            adapter_name="mcp",
        )
        resp = await engine.execute(req)
        if resp.error:
            return f"Error: {resp.error}"
        return resp.content

    @server.tool()
    async def auracode_explain(file_path: str) -> str:
        """Explain a file's contents."""
        from pathlib import Path

        from auracode.models.context import FileContext, SessionContext
        from auracode.models.request import EngineRequest, RequestIntent

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
        req = EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=RequestIntent.EXPLAIN_CODE,
            prompt=f"Explain the contents of {file_path}",
            context=session,
            adapter_name="mcp",
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
        from auracode.models.request import EngineRequest, RequestIntent

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
        req = EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=RequestIntent.REVIEW,
            prompt=f"Review the code in {file_path}",
            context=session,
            adapter_name="mcp",
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

    return server
