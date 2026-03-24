"""Output formatting for OpenCode adapter responses."""

from __future__ import annotations

from auracode.models.request import EngineResponse, FileArtifact


def _format_artifact(artifact: FileArtifact) -> str:
    """Render a single file artifact as a clean markdown block."""
    action_label = {
        "create": "Created",
        "modify": "Modified",
        "delete": "Deleted",
    }.get(artifact.action, artifact.action)

    lines = [f"\n**{action_label}:** `{artifact.path}`"]
    if artifact.action == "delete":
        lines.append("*(file removed)*")
    else:
        ext = artifact.path.rsplit(".", 1)[-1] if "." in artifact.path else ""
        lines.append(f"```{ext}")
        lines.append(artifact.content)
        lines.append("```")
    return "\n".join(lines)


def format_response(
    response: EngineResponse,
    *,
    show_model: bool = True,
    show_usage: bool = False,
) -> str:
    """Format an EngineResponse for terminal display.

    Parameters
    ----------
    response:
        The engine response to format.
    show_model:
        If True, show model attribution subtly in a footer line.
    show_usage:
        If True, show token usage in the footer.
    """
    parts: list[str] = []

    # Main content
    if response.content:
        parts.append(response.content)

    # File artifacts
    if response.artifacts:
        parts.append("\n---")
        for artifact in response.artifacts:
            parts.append(_format_artifact(artifact))

    # Subtle footer
    footer_items: list[str] = []
    if show_model and response.model_used:
        footer_items.append(response.model_used)
    if show_usage and response.usage:
        total = response.usage.prompt_tokens + response.usage.completion_tokens
        footer_items.append(
            f"{response.usage.prompt_tokens}+{response.usage.completion_tokens}={total} tokens"
        )
    if footer_items:
        parts.append("\n*" + " | ".join(footer_items) + "*")

    # Error
    if response.error:
        parts.append(f"\n**Error:** {response.error}")

    return "\n".join(parts)
