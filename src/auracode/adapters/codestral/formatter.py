"""Output formatting for Codestral adapter responses."""

from __future__ import annotations

from auracode.models.request import EngineResponse


def format_response(response: EngineResponse) -> str:
    """Format an EngineResponse for Codestral-style output.

    For completion/generation intents, returns raw code (no markdown wrapping).
    For chat intents, returns standard markdown.
    """
    parts: list[str] = []

    # For completions, emit raw code from artifacts without markdown fencing.
    if response.artifacts:
        for artifact in response.artifacts:
            if artifact.action == "delete":
                parts.append(f"# deleted: {artifact.path}")
            else:
                parts.append(artifact.content)

    # Main content — always included.
    if response.content:
        parts.append(response.content)

    # Error
    if response.error:
        parts.append(f"Error: {response.error}")

    return "\n".join(parts)
