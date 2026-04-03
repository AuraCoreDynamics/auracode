"""Map AuraCode request intents to AuraRouter roles and capability profiles."""

from __future__ import annotations

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent

_MAX_FILE_CHARS = 8_000  # Truncation limit per file in context prompt
_MAX_CONTEXT_CHARS = 80_000  # Hard cap on total context prompt length

DIFF_THRESHOLD_CHARS = 6_000  # ~1500 tokens at ~4 chars/token

INTENT_ROLE_MAP: dict[RequestIntent, str] = {
    RequestIntent.GENERATE_CODE: "coder",
    RequestIntent.EDIT_CODE: "coder",
    RequestIntent.COMPLETE_CODE: "coder",
    RequestIntent.EXPLAIN_CODE: "reasoning",
    RequestIntent.REVIEW: "reasoning",
    RequestIntent.CHAT: "reasoning",
    RequestIntent.PLAN: "reasoning",
    RequestIntent.REFACTOR: "coder",
    RequestIntent.REVIEW_DIFF: "reasoning",
    RequestIntent.SECURITY_REVIEW: "reasoning",
    RequestIntent.GENERATE_TESTS: "coder",
    RequestIntent.CROSS_FILE_EDIT: "coder",
    RequestIntent.ARCHITECTURE_TRACE: "reasoning",
}

# Capability profile per intent — what backend features the intent benefits from.
INTENT_CAPABILITY_MAP: dict[RequestIntent, list[str]] = {
    RequestIntent.GENERATE_CODE: ["code_generation"],
    RequestIntent.EDIT_CODE: ["code_generation", "diff_aware"],
    RequestIntent.COMPLETE_CODE: ["code_completion", "low_latency"],
    RequestIntent.EXPLAIN_CODE: ["reasoning", "context_analysis"],
    RequestIntent.REVIEW: ["reasoning", "security_analysis"],
    RequestIntent.CHAT: ["reasoning"],
    RequestIntent.PLAN: ["reasoning", "architecture"],
    RequestIntent.REFACTOR: ["code_generation", "diff_aware", "cross_file"],
    RequestIntent.REVIEW_DIFF: ["reasoning", "diff_aware"],
    RequestIntent.SECURITY_REVIEW: ["reasoning", "security_analysis"],
    RequestIntent.GENERATE_TESTS: ["code_generation", "test_aware"],
    RequestIntent.CROSS_FILE_EDIT: ["code_generation", "cross_file"],
    RequestIntent.ARCHITECTURE_TRACE: ["reasoning", "architecture", "cross_file"],
}


def classify_modification_type(file_ctx: FileContext) -> str:
    """Return ``'unified_diff'`` for large files, ``'full_rewrite'`` for small.

    The decision is based on a simple character-length heuristic
    (see :data:`DIFF_THRESHOLD_CHARS`).  This is O(1) per file — no
    tokenizer calls, just ``len(content)``.
    """
    if file_ctx.content is None:
        return "full_rewrite"  # no content to diff against
    if len(file_ctx.content) > DIFF_THRESHOLD_CHARS:
        return "unified_diff"
    return "full_rewrite"


def build_file_constraints(context: SessionContext | None) -> list[dict[str, str]]:
    """Build per-file modification type preferences.

    Returns an empty list when *context* is ``None`` or has no files.
    """
    if context is None:
        return []
    return [
        {
            "path": f.path,
            "preferred_modification": classify_modification_type(f),
        }
        for f in context.files
    ]


def map_intent_to_role(intent: RequestIntent) -> str:
    """Return the AuraRouter role name for *intent*.

    Falls back to ``"reasoning"`` for unknown intents.
    """
    return INTENT_ROLE_MAP.get(intent, "reasoning")


def map_intent_to_capabilities(intent: RequestIntent) -> list[str]:
    """Return the capability profile for *intent*."""
    return INTENT_CAPABILITY_MAP.get(intent, [])


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
    """Build a prompt prefix from session context (files, history, semantics).

    Returns an empty string when *context* is ``None`` or has no meaningful
    content.  The total output is hard-capped at :data:`_MAX_CONTEXT_CHARS`
    to prevent unbounded prompt growth.
    """
    if context is None:
        return ""

    parts: list[str] = []

    # Context semantics — project/sensitivity/diff hints
    sem_parts: list[str] = []
    if context.project_id:
        sem_parts.append(f"Project: {context.project_id}")
    if context.sensitivity_label:
        sem_parts.append(f"Sensitivity: {context.sensitivity_label}")
    if context.changed_files:
        sem_parts.append(f"Changed files: {', '.join(context.changed_files[:20])}")
    if context.diff_summary:
        sem_parts.append(f"Diff summary: {context.diff_summary[:500]}")
    if context.retrieval_hints:
        sem_parts.append(f"Retrieval hints: {', '.join(context.retrieval_hints[:10])}")
    if sem_parts:
        parts.append("## Context\n" + "\n".join(sem_parts))

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

    result = "\n".join(parts) + "\n\n"

    # Enforce hard cap on total context length.
    if len(result) > _MAX_CONTEXT_CHARS:
        result = result[:_MAX_CONTEXT_CHARS] + "\n... (context truncated)\n\n"

    return result
