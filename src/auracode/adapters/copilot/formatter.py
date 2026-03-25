"""Output formatting for Copilot adapter responses."""

from __future__ import annotations

from auracode.models.request import EngineResponse, FileArtifact


def _format_artifact(artifact: FileArtifact) -> str:
    """Render a single file artifact as a language-tagged code block."""
    ext = artifact.path.rsplit(".", 1)[-1] if "." in artifact.path else ""
    if artifact.action == "delete":
        return f"\n`{artifact.path}` — *deleted*"
    lines = [f"\n`{artifact.path}`"]
    lines.append(f"```{ext}")
    lines.append(artifact.content)
    lines.append("```")
    return "\n".join(lines)


def format_response(response: EngineResponse) -> str:
    """Format an EngineResponse as a Copilot-style inline suggestion.

    Layout:
        ## Suggestion
        <language-tagged code block(s)>

        ## Explanation  (if non-code content present)
        <explanation text>
    """
    parts: list[str] = []

    # If there are artifacts, render them under a Suggestion header.
    if response.artifacts:
        parts.append("## Suggestion")
        for artifact in response.artifacts:
            parts.append(_format_artifact(artifact))

    # Main content as explanation.
    if response.content:
        if response.artifacts:
            parts.append("\n## Explanation")
        parts.append(response.content)

    # Error
    if response.error:
        parts.append(f"\n**Error:** {response.error}")

    return "\n".join(parts)
