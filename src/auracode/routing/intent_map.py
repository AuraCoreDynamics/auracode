"""Map AuraCode request intents to AuraRouter roles."""

from __future__ import annotations

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent

_MAX_FILE_CHARS = 8_000  # Truncation limit per file in context prompt

INTENT_ROLE_MAP: dict[RequestIntent, str] = {
    RequestIntent.GENERATE_CODE: "coder",
    RequestIntent.EDIT_CODE: "coder",
    RequestIntent.COMPLETE_CODE: "coder",
    RequestIntent.EXPLAIN_CODE: "reasoning",
    RequestIntent.REVIEW: "reasoning",
    RequestIntent.CHAT: "reasoning",
    RequestIntent.PLAN: "reasoning",
}


def map_intent_to_role(intent: RequestIntent) -> str:
    """Return the AuraRouter role name for *intent*.

    Raises ``KeyError`` if the intent is unknown.
    """
    return INTENT_ROLE_MAP[intent]


def _format_file(fc: FileContext) -> str:
    """Format a single ``FileContext`` for inclusion in a prompt."""
    header = f"--- {fc.path}"
    if fc.language:
        header += f" ({fc.language})"
    if fc.selection:
        header += f" [lines {fc.selection[0]}-{fc.selection[1]}]"
    header += " ---"

    if fc.content is None:
        return header + "\n(no content available)\n"

    body = fc.content
    if len(body) > _MAX_FILE_CHARS:
        body = body[:_MAX_FILE_CHARS] + "\n... (truncated)"

    return f"{header}\n{body}\n"


def build_context_prompt(context: SessionContext | None) -> str:
    """Build a prompt prefix from session context (files, history).

    Returns an empty string when *context* is ``None`` or has no meaningful
    content.
    """
    if context is None:
        return ""

    parts: list[str] = []

    # File contents
    if context.files:
        parts.append("## Active Files\n")
        for fc in context.files:
            parts.append(_format_file(fc))

    # Recent conversation history
    if context.history:
        parts.append("## Conversation History\n")
        for msg in context.history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"[{role}]: {content}")

    if not parts:
        return ""

    return "\n".join(parts) + "\n\n"
