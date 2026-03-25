"""Output formatting for Aider adapter responses."""

from __future__ import annotations

from auracode.models.request import EngineResponse, FileArtifact


def _format_artifact_as_diff(artifact: FileArtifact) -> str:
    """Render a single file artifact as a unified diff block."""
    lines: list[str] = []
    if artifact.action == "create":
        lines.append("--- /dev/null")
        lines.append(f"+++ {artifact.path}")
        for line in artifact.content.splitlines():
            lines.append(f"+{line}")
    elif artifact.action == "delete":
        lines.append(f"--- {artifact.path}")
        lines.append("+++ /dev/null")
        lines.append("-# (file deleted)")
    else:  # modify
        lines.append(f"--- {artifact.path}")
        lines.append(f"+++ {artifact.path}")
        for line in artifact.content.splitlines():
            lines.append(f"+{line}")
    return "\n".join(lines)


def format_response(response: EngineResponse) -> str:
    """Format an EngineResponse as Aider-style diff output.

    If the response has file artifacts, renders them as unified diff blocks.
    Otherwise, renders as plain markdown.
    """
    parts: list[str] = []

    # File artifacts as diffs.
    if response.artifacts:
        for artifact in response.artifacts:
            parts.append(_format_artifact_as_diff(artifact))
    elif response.content:
        # Plain markdown for non-code responses.
        parts.append(response.content)

    # If there's content alongside artifacts, append it after the diffs.
    if response.artifacts and response.content:
        parts.append("")
        parts.append(response.content)

    # Error
    if response.error:
        parts.append(f"\n**Error:** {response.error}")

    return "\n".join(parts)
