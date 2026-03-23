"""Tests for intent-to-role mapping and context prompt builder."""

from __future__ import annotations

import pytest

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.intent_map import (
    INTENT_ROLE_MAP,
    build_context_prompt,
    map_intent_to_role,
)


# ---------------------------------------------------------------------------
# map_intent_to_role
# ---------------------------------------------------------------------------


class TestMapIntentToRole:
    """Every RequestIntent member must have a mapping."""

    def test_all_intents_mapped(self):
        for intent in RequestIntent:
            assert intent in INTENT_ROLE_MAP, f"{intent} missing from INTENT_ROLE_MAP"

    @pytest.mark.parametrize(
        "intent",
        [RequestIntent.GENERATE_CODE, RequestIntent.EDIT_CODE, RequestIntent.COMPLETE_CODE],
    )
    def test_code_intents_map_to_coder(self, intent: RequestIntent):
        assert map_intent_to_role(intent) == "coder"

    @pytest.mark.parametrize(
        "intent",
        [RequestIntent.EXPLAIN_CODE, RequestIntent.REVIEW, RequestIntent.CHAT, RequestIntent.PLAN],
    )
    def test_reasoning_intents_map_to_reasoning(self, intent: RequestIntent):
        assert map_intent_to_role(intent) == "reasoning"


# ---------------------------------------------------------------------------
# build_context_prompt
# ---------------------------------------------------------------------------


class TestBuildContextPrompt:
    def test_none_context_returns_empty(self):
        assert build_context_prompt(None) == ""

    def test_empty_context_returns_empty(self):
        ctx = SessionContext(session_id="s1", working_directory="/tmp")
        assert build_context_prompt(ctx) == ""

    def test_files_included(self):
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="main.py", content="print('hi')", language="python"),
            ],
        )
        result = build_context_prompt(ctx)
        assert "main.py" in result
        assert "python" in result
        assert "print('hi')" in result

    def test_file_without_content(self):
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[FileContext(path="empty.py")],
        )
        result = build_context_prompt(ctx)
        assert "empty.py" in result
        assert "no content available" in result

    def test_file_with_selection(self):
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="lib.py", content="x=1", selection=(10, 20)),
            ],
        )
        result = build_context_prompt(ctx)
        assert "lines 10-20" in result

    def test_large_file_truncated(self):
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[
                FileContext(path="big.py", content="x" * 20_000),
            ],
        )
        result = build_context_prompt(ctx)
        assert "truncated" in result
        # Result must be shorter than the raw content.
        assert len(result) < 20_000

    def test_history_included(self):
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ],
        )
        result = build_context_prompt(ctx)
        assert "[user]: Hello" in result
        assert "[assistant]: Hi there" in result

    def test_files_and_history_together(self):
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[FileContext(path="a.py", content="code")],
            history=[{"role": "user", "content": "help"}],
        )
        result = build_context_prompt(ctx)
        assert "Active Files" in result
        assert "Conversation History" in result
