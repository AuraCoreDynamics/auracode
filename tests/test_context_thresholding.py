"""Tests for context thresholding and diff heuristics (Task Group 2)."""

from __future__ import annotations

from auracode.models.context import FileContext, SessionContext
from auracode.routing.intent_map import (
    DIFF_THRESHOLD_CHARS,
    build_file_constraints,
    classify_modification_type,
)

# ---------------------------------------------------------------------------
# classify_modification_type
# ---------------------------------------------------------------------------


class TestClassifyModificationType:
    def test_none_content_returns_full_rewrite(self):
        fc = FileContext(path="empty.py", content=None)
        assert classify_modification_type(fc) == "full_rewrite"

    def test_short_content_returns_full_rewrite(self):
        fc = FileContext(path="small.py", content="x = 1")
        assert classify_modification_type(fc) == "full_rewrite"

    def test_content_exactly_at_threshold_returns_full_rewrite(self):
        fc = FileContext(path="boundary.py", content="a" * DIFF_THRESHOLD_CHARS)
        assert classify_modification_type(fc) == "full_rewrite"

    def test_content_above_threshold_returns_unified_diff(self):
        fc = FileContext(path="big.py", content="a" * (DIFF_THRESHOLD_CHARS + 1))
        assert classify_modification_type(fc) == "unified_diff"

    def test_empty_string_content_returns_full_rewrite(self):
        fc = FileContext(path="blank.py", content="")
        assert classify_modification_type(fc) == "full_rewrite"


# ---------------------------------------------------------------------------
# build_file_constraints
# ---------------------------------------------------------------------------


class TestBuildFileConstraints:
    def test_none_context_returns_empty_list(self):
        assert build_file_constraints(None) == []

    def test_empty_file_list_returns_empty_list(self):
        ctx = SessionContext(session_id="s1", working_directory="/tmp", files=[])
        assert build_file_constraints(ctx) == []

    def test_mixed_files_classified_correctly(self):
        small = FileContext(path="small.py", content="x = 1")
        large = FileContext(path="large.py", content="y" * (DIFF_THRESHOLD_CHARS + 1))
        no_content = FileContext(path="none.py", content=None)

        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[small, large, no_content],
        )
        result = build_file_constraints(ctx)

        assert len(result) == 3
        assert result[0] == {"path": "small.py", "preferred_modification": "full_rewrite"}
        assert result[1] == {"path": "large.py", "preferred_modification": "unified_diff"}
        assert result[2] == {"path": "none.py", "preferred_modification": "full_rewrite"}

    def test_single_large_file(self):
        fc = FileContext(path="huge.py", content="z" * 20_000)
        ctx = SessionContext(session_id="s1", working_directory="/tmp", files=[fc])
        result = build_file_constraints(ctx)

        assert len(result) == 1
        assert result[0]["preferred_modification"] == "unified_diff"


# ---------------------------------------------------------------------------
# DIFF_THRESHOLD_CHARS constant
# ---------------------------------------------------------------------------


class TestDiffThresholdConstant:
    def test_threshold_value(self):
        assert DIFF_THRESHOLD_CHARS == 6000
