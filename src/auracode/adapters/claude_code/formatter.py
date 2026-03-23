"""Output formatting for Claude Code adapter responses."""

from __future__ import annotations

import json as _json
from typing import Any

from auracode.models.request import EngineResponse, FileArtifact


def _format_artifact(artifact: FileArtifact) -> str:
    """Render a single file artifact as a markdown diff block."""
    action_label = {
        "create": "+++ new file",
        "modify": "~~~ modified",
        "delete": "--- deleted",
    }.get(artifact.action, artifact.action)

    lines = [
        f"\n### {action_label}: `{artifact.path}`",
    ]
    if artifact.action == "delete":
        lines.append("*(file removed)*")
    else:
        # Guess a language hint from the file extension.
        ext = artifact.path.rsplit(".", 1)[-1] if "." in artifact.path else ""
        lines.append(f"```{ext}")
        lines.append(artifact.content)
        lines.append("```")
    return "\n".join(lines)


def format_response(response: EngineResponse, *, json_mode: bool = False) -> str:
    """Format an *EngineResponse* for terminal display.

    Parameters
    ----------
    response:
        The engine response to format.
    json_mode:
        If ``True``, return a JSON serialization of the response.
        Otherwise return human-friendly markdown-style text.
    """
    if json_mode:
        return response.model_dump_json(indent=2)

    parts: list[str] = []

    # Main content
    if response.content:
        parts.append(response.content)

    # File artifacts
    if response.artifacts:
        parts.append("\n---\n**File Artifacts:**")
        for artifact in response.artifacts:
            parts.append(_format_artifact(artifact))

    # Metadata footer
    footer_items: list[str] = []
    if response.model_used:
        footer_items.append(f"model: {response.model_used}")
    if response.usage:
        total = response.usage.prompt_tokens + response.usage.completion_tokens
        footer_items.append(
            f"tokens: {response.usage.prompt_tokens}+{response.usage.completion_tokens}={total}"
        )
    if footer_items:
        parts.append("\n" + " | ".join(footer_items))

    # Error
    if response.error:
        parts.append(f"\n**Error:** {response.error}")

    return "\n".join(parts)
