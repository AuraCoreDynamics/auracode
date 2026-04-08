"""CopilotAdapter — emulates GitHub Copilot CLI's interaction model."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import click

from auracode.adapters.base import BaseAdapter
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent

# Maps raw intent strings to RequestIntent enums.
_INTENT_MAP: dict[str, RequestIntent] = {
    "suggest": RequestIntent.GENERATE_CODE,
    "explain": RequestIntent.EXPLAIN_CODE,
    "commit": RequestIntent.GENERATE_CODE,
}


def _read_git_head(working_dir: str) -> str | None:
    """Return the current git ref for *working_dir*, or None if unavailable."""
    head_path = os.path.normpath(os.path.join(working_dir, ".git", "HEAD"))
    try:
        with open(head_path, encoding="utf-8") as fh:
            ref = fh.read().strip()
        return ref[5:] if ref.startswith("ref: ") else ref
    except OSError:
        return None


class CopilotAdapter(BaseAdapter):
    """Adapter that emulates GitHub Copilot CLI's interaction model."""

    @property
    def name(self) -> str:
        return "copilot"

    async def translate_request(self, raw_input: Any) -> EngineRequest:
        """Convert a dict with prompt/intent/context_files/options to EngineRequest.

        Expected *raw_input* keys:
            - ``prompt`` (str, required)
            - ``intent`` (str, optional -- defaults to ``"suggest"``)
            - ``context_files`` (list[str], optional -- file paths)
            - ``options`` (dict, optional -- supports ``workspace_root``)
        """
        if not isinstance(raw_input, dict):
            raise TypeError(f"Expected dict, got {type(raw_input).__name__}")

        prompt: str = raw_input.get("prompt", "")
        intent_key: str = raw_input.get("intent", "suggest")
        intent = _INTENT_MAP.get(intent_key, RequestIntent.GENERATE_CODE)

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

        options: dict[str, Any] = raw_input.get("options", {})
        working_dir = options.get("workspace_root", str(Path.cwd()))
        project_id: str = Path(working_dir).name or "unknown"
        sensitivity_label: str = options.get("sensitivity_label", "unclassified")

        session_context: SessionContext | None = None
        if file_contexts:
            session_context = SessionContext(
                session_id=str(uuid.uuid4()),
                working_directory=working_dir,
                files=file_contexts,
                project_id=project_id,
                sensitivity_label=sensitivity_label,
            )

        # For commit intent, set a flag in options.
        if intent_key == "commit":
            options = {**options, "commit": True}

        git_ref = _read_git_head(working_dir)
        if git_ref is not None:
            options = {**options, "git_ref": git_ref}

        return EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=intent,
            prompt=prompt,
            context=session_context,
            adapter_name=self.name,
            options=options,
        )

    async def translate_response(self, response: EngineResponse) -> Any:
        """Convert an EngineResponse to Copilot-style inline suggestion output."""
        from auracode.adapters.copilot.formatter import format_response

        return format_response(response)

    def get_cli_group(self) -> click.Group | None:
        """Return the Click group for the Copilot adapter."""
        from auracode.adapters.copilot.cli import copilot

        return copilot
