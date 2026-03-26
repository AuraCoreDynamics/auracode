"""Tests for the structured artifact parser and transactional executor."""

from __future__ import annotations

import importlib
import json
import sys
import textwrap
from types import ModuleType
from unittest.mock import MagicMock

from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.artifacts import (
    ArtifactPayload,
    FileModification,
    execute_modifications,
    parse_artifact_payload,
)

# ===================================================================
# Parser tests
# ===================================================================


class TestParseArtifactPayload:
    def test_valid_json_single_modification(self):
        raw = json.dumps(
            {
                "modifications": [
                    {
                        "file_path": "src/foo.py",
                        "modification_type": "full_rewrite",
                        "content": "# hello",
                        "language": "python",
                    }
                ]
            }
        )
        payload = parse_artifact_payload(raw)
        assert payload is not None
        assert len(payload.modifications) == 1
        mod = payload.modifications[0]
        assert mod.file_path == "src/foo.py"
        assert mod.modification_type == "full_rewrite"
        assert mod.content == "# hello"
        assert mod.language == "python"

    def test_valid_json_multiple_modifications(self):
        raw = json.dumps(
            {
                "modifications": [
                    {
                        "file_path": "a.py",
                        "modification_type": "full_rewrite",
                        "content": "a",
                        "language": "python",
                    },
                    {
                        "file_path": "b.py",
                        "modification_type": "unified_diff",
                        "content": "diff",
                        "language": "python",
                    },
                ]
            }
        )
        payload = parse_artifact_payload(raw)
        assert payload is not None
        assert len(payload.modifications) == 2

    def test_non_json_returns_none(self):
        assert parse_artifact_payload("this is plain text") is None

    def test_empty_string_returns_none(self):
        assert parse_artifact_payload("") is None

    def test_json_array_returns_none(self):
        assert parse_artifact_payload("[1, 2, 3]") is None

    def test_missing_modifications_key_returns_none(self):
        assert parse_artifact_payload('{"foo": "bar"}') is None

    def test_modifications_not_a_list_returns_none(self):
        assert parse_artifact_payload('{"modifications": "oops"}') is None

    def test_malformed_entries_skipped(self):
        raw = json.dumps(
            {
                "modifications": [
                    {"file_path": "a.py"},  # missing fields
                    {
                        "file_path": "b.py",
                        "modification_type": "full_rewrite",
                        "content": "ok",
                        "language": "python",
                    },
                    "not a dict",
                ]
            }
        )
        payload = parse_artifact_payload(raw)
        assert payload is not None
        assert len(payload.modifications) == 1
        assert payload.modifications[0].file_path == "b.py"

    def test_empty_modifications_list(self):
        raw = json.dumps({"modifications": []})
        payload = parse_artifact_payload(raw)
        assert payload is not None
        assert len(payload.modifications) == 0


# ===================================================================
# Path validation tests
# ===================================================================


class TestPathValidation:
    def test_path_within_working_dir(self, tmp_path):
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="hello.py",
                    modification_type="full_rewrite",
                    content="print('hi')",
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert len(results) == 1
        assert results[0].success

    def test_path_traversal_rejected(self, tmp_path):
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="../../../etc/passwd",
                    modification_type="full_rewrite",
                    content="bad",
                    language="text",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert len(results) == 1
        assert not results[0].success
        assert "path traversal" in results[0].error

    def test_absolute_path_outside_rejected(self, tmp_path):
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="/tmp/outside.py",
                    modification_type="full_rewrite",
                    content="bad",
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert len(results) == 1
        assert not results[0].success


# ===================================================================
# Full rewrite tests
# ===================================================================


class TestFullRewrite:
    def test_write_new_file_with_parent_dirs(self, tmp_path):
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="sub/dir/new.py",
                    modification_type="full_rewrite",
                    content="# new file\n",
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert results[0].success
        written = (tmp_path / "sub" / "dir" / "new.py").read_text()
        assert written == "# new file\n"

    def test_overwrite_existing_file(self, tmp_path):
        existing = tmp_path / "app.py"
        existing.write_text("old content")

        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="app.py",
                    modification_type="full_rewrite",
                    content="new content",
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert results[0].success
        assert existing.read_text() == "new content"

    def test_strategy_used_is_none_for_full_rewrite(self, tmp_path):
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="x.py",
                    modification_type="full_rewrite",
                    content="x",
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert results[0].strategy_used is None


# ===================================================================
# Unified diff tests
# ===================================================================


class TestUnifiedDiff:
    def test_strict_mode_apply(self, tmp_path):
        original = "line1\nline2\nline3\n"
        (tmp_path / "f.py").write_text(original)

        diff = textwrap.dedent("""\
            --- a/f.py
            +++ b/f.py
            @@ -2,1 +2,1 @@
            -line2
            +replaced
        """)

        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="f.py",
                    modification_type="unified_diff",
                    content=diff,
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert results[0].success
        assert results[0].strategy_used == "strict"
        assert "replaced" in (tmp_path / "f.py").read_text()

    def test_fuzzy_fallback_wrong_line_numbers(self, tmp_path):
        original = "alpha\nbeta\ngamma\n"
        (tmp_path / "g.py").write_text(original)

        # Deliberately wrong line numbers, but correct content to match.
        diff = textwrap.dedent("""\
            --- a/g.py
            +++ b/g.py
            @@ -99,1 +99,1 @@
            -beta
            +BETA
        """)

        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="g.py",
                    modification_type="unified_diff",
                    content=diff,
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert results[0].success
        assert results[0].strategy_used == "fuzzy"
        assert "BETA" in (tmp_path / "g.py").read_text()

    def test_diff_total_failure(self, tmp_path):
        (tmp_path / "h.py").write_text("hello\n")

        diff = textwrap.dedent("""\
            --- a/h.py
            +++ b/h.py
            @@ -1,1 +1,1 @@
            -no_match_here
            +replaced
        """)

        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="h.py",
                    modification_type="unified_diff",
                    content=diff,
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert not results[0].success
        assert results[0].error is not None
        # File should be rolled back to original.
        assert (tmp_path / "h.py").read_text() == "hello\n"

    def test_diff_on_nonexistent_file_fails(self, tmp_path):
        diff = textwrap.dedent("""\
            --- a/missing.py
            +++ b/missing.py
            @@ -1,1 +1,1 @@
            -old
            +new
        """)
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="missing.py",
                    modification_type="unified_diff",
                    content=diff,
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert not results[0].success


# ===================================================================
# Transactional rollback tests
# ===================================================================


class TestTransactionalRollback:
    def test_three_files_second_fails_first_restored_third_not_written(self, tmp_path):
        # File 1 exists, will be overwritten.
        (tmp_path / "a.py").write_text("original_a")
        # File 2 exists, diff will fail.
        (tmp_path / "b.py").write_text("original_b")
        # File 3 does not exist, would be created.

        bad_diff = textwrap.dedent("""\
            --- a/b.py
            +++ b/b.py
            @@ -1,1 +1,1 @@
            -WILL_NOT_MATCH
            +replacement
        """)

        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="a.py",
                    modification_type="full_rewrite",
                    content="new_a",
                    language="python",
                ),
                FileModification(
                    file_path="b.py",
                    modification_type="unified_diff",
                    content=bad_diff,
                    language="python",
                ),
                FileModification(
                    file_path="c.py",
                    modification_type="full_rewrite",
                    content="new_c",
                    language="python",
                ),
            ]
        )
        results = execute_modifications(payload, str(tmp_path))

        # b.py failed.
        assert not results[1].success

        # a.py should be restored to original.
        assert (tmp_path / "a.py").read_text() == "original_a"

        # c.py should not exist (never written, or deleted).
        assert not (tmp_path / "c.py").exists()

    def test_new_file_created_then_rollback_deletes_it(self, tmp_path):
        # File 1: new (will succeed).
        # File 2: diff on existing (will fail).
        (tmp_path / "existing.py").write_text("keep me")

        bad_diff = textwrap.dedent("""\
            --- a/existing.py
            +++ b/existing.py
            @@ -1,1 +1,1 @@
            -NOMATCH
            +replacement
        """)

        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="brand_new.py",
                    modification_type="full_rewrite",
                    content="hello",
                    language="python",
                ),
                FileModification(
                    file_path="existing.py",
                    modification_type="unified_diff",
                    content=bad_diff,
                    language="python",
                ),
            ]
        )
        results = execute_modifications(payload, str(tmp_path))

        assert not results[1].success
        # brand_new.py was created but should be deleted on rollback.
        assert not (tmp_path / "brand_new.py").exists()
        # existing.py should be restored.
        assert (tmp_path / "existing.py").read_text() == "keep me"


# ===================================================================
# Execution trace / strategy_used tests
# ===================================================================


class TestExecutionTrace:
    def test_strategy_used_populated(self, tmp_path):
        (tmp_path / "s.py").write_text("one\ntwo\nthree\n")
        diff = textwrap.dedent("""\
            --- a/s.py
            +++ b/s.py
            @@ -2,1 +2,1 @@
            -two
            +TWO
        """)
        payload = ArtifactPayload(
            modifications=[
                FileModification(
                    file_path="s.py",
                    modification_type="unified_diff",
                    content=diff,
                    language="python",
                )
            ]
        )
        results = execute_modifications(payload, str(tmp_path))
        assert results[0].success
        assert results[0].strategy_used in ("strict", "fuzzy")


# ===================================================================
# Integration: route() merges upstream + executor trace
# ===================================================================


def _build_mock_aurarouter_modules(fabric_response: str):
    """Create mock aurarouter modules returning the given fabric response."""
    ar = ModuleType("aurarouter")
    ar_config = ModuleType("aurarouter.config")
    ar_fabric = ModuleType("aurarouter.fabric")

    config_loader = MagicMock()
    config_loader.config = {"models": {"m1": {"provider": "test"}}, "roles": {"coder": ["m1"]}}
    config_loader.get_role_chain = MagicMock(side_effect=lambda role: ["m1"])
    config_loader.get_all_model_ids = MagicMock(return_value=["m1"])
    config_loader.get_model_config = MagicMock(return_value={"provider": "test"})

    fabric = MagicMock()
    fabric.execute = MagicMock(return_value=fabric_response)

    ar_config.ConfigLoader = MagicMock(return_value=config_loader)
    ar_fabric.ComputeFabric = MagicMock(return_value=fabric)

    return {
        "aurarouter": ar,
        "aurarouter.config": ar_config,
        "aurarouter.fabric": ar_fabric,
        "fabric": fabric,
        "config_loader": config_loader,
    }


class TestRouteIntegration:
    async def test_route_with_edit_code_writes_files_and_populates_metadata(self, tmp_path):
        artifact_json = json.dumps(
            {
                "modifications": [
                    {
                        "file_path": "out.py",
                        "modification_type": "full_rewrite",
                        "content": "print('hello')\n",
                        "language": "python",
                    }
                ]
            }
        )

        mocks = _build_mock_aurarouter_modules(artifact_json)
        originals = {}
        for key in ("aurarouter", "aurarouter.config", "aurarouter.fabric"):
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            import auracode.routing.embedded as mod

            importlib.reload(mod)
            backend = mod.EmbeddedRouterBackend()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
            )
            result = await backend.route(
                prompt="create out.py",
                intent=RequestIntent.EDIT_CODE,
                context=ctx,
            )

            # File should exist.
            assert (tmp_path / "out.py").read_text() == "print('hello')\n"

            # Metadata should contain artifact_execution.
            assert "artifact_execution" in result.metadata
            execs = result.metadata["artifact_execution"]
            assert len(execs) == 1
            assert execs[0]["file"] == "out.py"
            assert execs[0]["ok"] is True

            # Execution trace should be present.
            assert "execution_trace" in result.metadata
            trace = result.metadata["execution_trace"]
            assert any("out.py" in t for t in trace)

        finally:
            for key in ("aurarouter", "aurarouter.config", "aurarouter.fabric"):
                if originals.get(key) is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            importlib.reload(mod)

    async def test_route_with_chat_intent_does_not_execute_artifacts(self, tmp_path):
        """Non-actionable intents should NOT trigger artifact execution."""
        artifact_json = json.dumps(
            {
                "modifications": [
                    {
                        "file_path": "should_not_exist.py",
                        "modification_type": "full_rewrite",
                        "content": "nope",
                        "language": "python",
                    }
                ]
            }
        )

        mocks = _build_mock_aurarouter_modules(artifact_json)
        originals = {}
        for key in ("aurarouter", "aurarouter.config", "aurarouter.fabric"):
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            import auracode.routing.embedded as mod

            importlib.reload(mod)
            backend = mod.EmbeddedRouterBackend()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
            )
            result = await backend.route(
                prompt="tell me about python",
                intent=RequestIntent.CHAT,
                context=ctx,
            )

            # File should NOT be written for CHAT intent.
            assert not (tmp_path / "should_not_exist.py").exists()
            assert "artifact_execution" not in result.metadata

        finally:
            for key in ("aurarouter", "aurarouter.config", "aurarouter.fabric"):
                if originals.get(key) is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            importlib.reload(mod)

    async def test_route_with_plain_text_response_no_artifact(self, tmp_path):
        """When the fabric returns plain text (not JSON), no artifact processing."""
        mocks = _build_mock_aurarouter_modules("Here is your code: def foo(): pass")
        originals = {}
        for key in ("aurarouter", "aurarouter.config", "aurarouter.fabric"):
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            import auracode.routing.embedded as mod

            importlib.reload(mod)
            backend = mod.EmbeddedRouterBackend()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
            )
            result = await backend.route(
                prompt="write foo",
                intent=RequestIntent.GENERATE_CODE,
                context=ctx,
            )

            assert result.content == "Here is your code: def foo(): pass"
            assert "artifact_execution" not in result.metadata

        finally:
            for key in ("aurarouter", "aurarouter.config", "aurarouter.fabric"):
                if originals.get(key) is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            importlib.reload(mod)
