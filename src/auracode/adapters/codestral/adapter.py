"""CodestralAdapter — targets inline code completion (FIM-style)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import click

from auracode.adapters.base import BaseAdapter
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import EngineRequest, EngineResponse, RequestIntent

# Maps raw intent strings to RequestIntent enums.
_INTENT_MAP: dict[str, RequestIntent] = {
    "complete": RequestIntent.COMPLETE_CODE,
    "fill": RequestIntent.GENERATE_CODE,
    "chat": RequestIntent.CHAT,
}


class CodestralAdapter(BaseAdapter):
    """Adapter that targets inline code completion with FIM support."""

    @property
    def name(self) -> str:
        return "codestral"

    async def translate_request(self, raw_input: Any) -> EngineRequest:
        """Convert a dict with prompt/intent/context_files/options to EngineRequest.

        Expected *raw_input* keys:
            - ``prompt`` (str, required)
            - ``intent`` (str, optional -- defaults to ``"complete"``)
            - ``context_files`` (list[str], optional -- file paths)
            - ``options`` (dict, optional -- supports ``prefix`` and ``suffix`` for FIM)
        """
        if not isinstance(raw_input, dict):
            raise TypeError(f"Expected dict, got {type(raw_input).__name__}")

        prompt: str = raw_input.get("prompt", "")
        intent_key: str = raw_input.get("intent", "complete")
        intent = _INTENT_MAP.get(intent_key, RequestIntent.COMPLETE_CODE)

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
        working_dir = str(Path.cwd())
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

        # FIM cache keying: hash prefix+suffix so downstream can deduplicate completions.
        prefix: str = options.get("prefix", "")
        suffix_text: str = options.get("suffix", "")
        if prefix or suffix_text:
            fim_key = hashlib.sha256(
                f"{prefix}\x00{suffix_text}".encode(), usedforsecurity=False
            ).hexdigest()[:16]
            options = {**options, "fim_cache_key": fim_key}

        return EngineRequest(
            request_id=str(uuid.uuid4()),
            intent=intent,
            prompt=prompt,
            context=session_context,
            adapter_name=self.name,
            options=options,
        )

    async def translate_response(self, response: EngineResponse) -> Any:
        """Convert an EngineResponse to Codestral-style completion output."""
        from auracode.adapters.codestral.formatter import format_response

        return format_response(response)

    def get_cli_group(self) -> click.Group | None:
        """Return the Click group for the Codestral adapter."""
        from auracode.adapters.codestral.cli import codestral

        return codestral
