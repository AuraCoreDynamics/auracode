"""ClaudeCodeAdapter — bridges the Claude Code CLI to the AuraCode engine."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import click

from auracode.adapters.base import BaseAdapter
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent


# Maps raw intent strings (as sent by the CLI layer) to RequestIntent enums.
_INTENT_MAP: dict[str, RequestIntent] = {
    "chat": RequestIntent.CHAT,
    "do": RequestIntent.GENERATE_CODE,
    "generate": RequestIntent.GENERATE_CODE,
    "explain": RequestIntent.EXPLAIN_CODE,
    "review": RequestIntent.REVIEW,
    "edit": RequestIntent.EDIT_CODE,
    "complete": RequestIntent.COMPLETE_CODE,
    "plan": RequestIntent.PLAN,
}


class ClaudeCodeAdapter(BaseAdapter):
    """Adapter that mimics the Claude Code CLI interface."""

    @property
    def name(self) -> str:
        return "claude-code"

    async def translate_request(self, raw_input: Any) -> EngineRequest:
        """Convert a dict with prompt/intent/context_files/options to EngineRequest.

        Expected *raw_input* keys:
            - ``prompt`` (str, required)
            - ``intent`` (str, optional — defaults to ``"chat"``)
            - ``context_files`` (list[str], optional — file paths)
            - ``options`` (dict, optional)
        """
        if not isinstance(raw_input, dict):
            raise TypeError(f"Expected dict, got {type(raw_input).__name__}")

        prompt: str = raw_input.get("prompt", "")
        intent_key: str = raw_input.get("intent", "chat")
        intent = _INTENT_MAP.get(intent_key, RequestIntent.CHAT)

        # Build file context from paths.
        context_files: list[str] = raw_input.get("context_files", [])
        file_contexts: list[FileContext] = []
        for path_str in context_files:
            p = Path(path_str)
            content: str | None = None
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    content = None
            suffix = p.suffix.lstrip(".")
            file_contexts.append(
                FileContext(
                    path=str(p),
                    content=content,
                    language=suffix or None,
                )
            )

        session_context: SessionContext | None = None
        if file_contexts:
            session_context = SessionContext(
                session_id=str(uuid.uuid4()),
                working_directory=str(Path.cwd()),
                files=file_contexts,
            )

        options: dict[str, Any] = raw_input.get("options", {})

        return EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=intent,
            prompt=prompt,
            context=session_context,
            adapter_name=self.name,
            options=options,
        )

    async def translate_response(self, response: EngineResponse) -> Any:
        """Convert an EngineResponse to a formatted markdown-style string."""
        from auracode.adapters.claude_code.formatter import format_response

        json_mode = False
        return format_response(response, json_mode=json_mode)

    def get_cli_group(self) -> click.Group | None:
        """Return the Click group for the Claude Code adapter."""
        from auracode.adapters.claude_code.cli import claude

        return claude
