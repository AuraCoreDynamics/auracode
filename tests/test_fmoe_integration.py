"""FMoE cross-component integration tests (Task Group 7).

Validates the end-to-end pipeline across AuraCode's routing layer:
- Options pipeline carries intent, routing_hints, file_constraints
- Schema enforcement produces parseable JSON for actionable intents
- Artifact consumer writes files correctly
- Fallback path is functionally identical to pre-upgrade behavior
- execution_trace is present in RouteResult.metadata for actionable intents
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent
from auracode.routing.artifacts import (
    execute_modifications,
    parse_artifact_payload,
)
from auracode.routing.intent_map import DIFF_THRESHOLD_CHARS

# ===================================================================
# Helpers
# ===================================================================


def _build_mock_aurarouter(fabric_response: str) -> dict:
    """Build mock aurarouter modules returning *fabric_response* from execute."""
    ar = ModuleType("aurarouter")
    ar_config = ModuleType("aurarouter.config")
    ar_fabric = ModuleType("aurarouter.fabric")

    config_loader = MagicMock()
    config_loader.config = {
        "models": {"m1": {"provider": "test"}},
        "roles": {"coder": ["m1"], "reasoning": ["m1"]},
    }
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


@pytest.fixture()
def _mock_router(request):
    """Inject mock aurarouter modules.

    Use ``@pytest.mark.parametrize("_mock_router", [...], indirect=True)``
    to supply the fabric response, or call with a default via the factory.
    """
    response = getattr(request, "param", "mock response")
    mocks = _build_mock_aurarouter(response)
    originals = {}
    keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
    for key in keys:
        originals[key] = sys.modules.get(key)
    sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})
    yield mocks
    for key in keys:
        if originals[key] is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = originals[key]


def _get_backend_cls():
    """Re-import EmbeddedRouterBackend so it picks up mocked modules."""
    import auracode.routing.embedded as mod

    importlib.reload(mod)
    return mod.EmbeddedRouterBackend


def _make_mixed_context(tmp_path: Path) -> SessionContext:
    """Create a SessionContext with mixed Python + TypeScript files.

    Includes large files (>DIFF_THRESHOLD_CHARS) and small files.
    """
    small_py = "print('hello')\n"
    small_ts = "console.log('hi');\n"
    large_py = "# large\n" + ("x = 1\n" * (DIFF_THRESHOLD_CHARS // 5 + 1))
    large_ts = "// large\n" + ("let x = 1;\n" * (DIFF_THRESHOLD_CHARS // 10 + 1))

    return SessionContext(
        session_id="integration-test",
        working_directory=str(tmp_path),
        files=[
            FileContext(path="small.py", content=small_py, language="python"),
            FileContext(path="small.ts", content=small_ts, language="typescript"),
            FileContext(path="large.py", content=large_py, language="python"),
            FileContext(path="large.ts", content=large_ts, language="typescript"),
        ],
    )


def _make_modifications_json(
    *mods: tuple[str, str, str, str],
) -> str:
    """Build a valid modifications JSON payload.

    Each tuple is (file_path, modification_type, content, language).
    """
    return json.dumps(
        {
            "modifications": [
                {
                    "file_path": fp,
                    "modification_type": mt,
                    "content": content,
                    "language": lang,
                }
                for fp, mt, content, lang in mods
            ]
        }
    )


# ===================================================================
# T7.1: Options Pipeline End-to-End
# ===================================================================


class TestOptionsPipeline:
    """Validate that intent, routing_hints, and file_constraints flow
    through the entire EmbeddedRouterBackend.route() pipeline."""

    async def test_options_carry_intent_hints_constraints(self, tmp_path):
        """Full pipeline: route() -> fabric.execute() receives correct options."""
        artifact_json = _make_modifications_json(
            ("out.py", "full_rewrite", "print(1)\n", "python"),
        )
        mocks = _build_mock_aurarouter(artifact_json)
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()
            ctx = _make_mixed_context(tmp_path)

            result = await backend.route(
                prompt="edit the files",
                intent=RequestIntent.EDIT_CODE,
                context=ctx,
            )

            # 1. Verify the options dict reaching the fabric
            fabric_call = mocks["fabric"].execute
            assert fabric_call.called
            call_kwargs = fabric_call.call_args
            passed_options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options", {})

            # 2. Options must contain intent, routing_hints, file_constraints
            assert passed_options["intent"] == "edit_code"
            assert "routing_hints" in passed_options
            assert sorted(passed_options["routing_hints"]) == ["python", "typescript"]

            # 3. file_constraints must be present and correct
            fc = passed_options["file_constraints"]
            assert isinstance(fc, list)
            assert len(fc) == 4  # 4 files

            fc_by_path = {c["path"]: c["preferred_modification"] for c in fc}
            assert fc_by_path["small.py"] == "full_rewrite"
            assert fc_by_path["small.ts"] == "full_rewrite"
            assert fc_by_path["large.py"] == "unified_diff"
            assert fc_by_path["large.ts"] == "unified_diff"

            # 4. RouteResult has artifact_execution and execution_trace
            assert "artifact_execution" in result.metadata
            assert "execution_trace" in result.metadata
            assert any("out.py" in t for t in result.metadata["execution_trace"])

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)

    async def test_file_constraints_classification(self, tmp_path):
        """Verify large files get unified_diff, small get full_rewrite."""
        mocks = _build_mock_aurarouter("plain text response")
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()
            ctx = _make_mixed_context(tmp_path)

            await backend.route(
                prompt="explain",
                intent=RequestIntent.EDIT_CODE,
                context=ctx,
            )

            opts = backend._last_route_options
            fc = opts["file_constraints"]
            large_files = [c for c in fc if c["preferred_modification"] == "unified_diff"]
            small_files = [c for c in fc if c["preferred_modification"] == "full_rewrite"]
            assert len(large_files) == 2
            assert len(small_files) == 2

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)


# ===================================================================
# T7.3: Schema Enforcement -> Artifact Consumer Round-Trip
# ===================================================================


class TestSchemaToArtifactRoundTrip:
    """Validate that MODIFICATIONS_SCHEMA-conforming payloads parse and
    execute correctly through the artifact pipeline."""

    def test_full_rewrite_round_trip(self, tmp_path):
        """Create -> parse -> execute a full_rewrite modification."""
        payload_json = _make_modifications_json(
            ("newfile.py", "full_rewrite", "def hello():\n    return 42\n", "python"),
        )

        payload = parse_artifact_payload(payload_json)
        assert payload is not None
        assert len(payload.modifications) == 1

        results = execute_modifications(payload, str(tmp_path))
        assert len(results) == 1
        assert results[0].success
        assert results[0].modification_type == "full_rewrite"

        written = (tmp_path / "newfile.py").read_text()
        assert "def hello" in written
        assert "return 42" in written

    def test_unified_diff_round_trip(self, tmp_path):
        """Create -> parse -> execute a unified_diff modification."""
        # Create the original file
        original = "line1\nline2\nline3\n"
        (tmp_path / "existing.py").write_text(original)

        diff = textwrap.dedent("""\
            --- a/existing.py
            +++ b/existing.py
            @@ -2,1 +2,1 @@
            -line2
            +REPLACED
        """)

        payload_json = _make_modifications_json(
            ("existing.py", "unified_diff", diff, "python"),
        )

        payload = parse_artifact_payload(payload_json)
        assert payload is not None

        results = execute_modifications(payload, str(tmp_path))
        assert len(results) == 1
        assert results[0].success
        assert results[0].modification_type == "unified_diff"

        content = (tmp_path / "existing.py").read_text()
        assert "REPLACED" in content
        assert "line2" not in content

    def test_mixed_modifications_round_trip(self, tmp_path):
        """Both full_rewrite and unified_diff in one payload."""
        (tmp_path / "old.py").write_text("alpha\nbeta\ngamma\n")

        diff = textwrap.dedent("""\
            --- a/old.py
            +++ b/old.py
            @@ -2,1 +2,1 @@
            -beta
            +BETA
        """)

        payload_json = _make_modifications_json(
            ("new.ts", "full_rewrite", "export const x = 1;\n", "typescript"),
            ("old.py", "unified_diff", diff, "python"),
        )

        payload = parse_artifact_payload(payload_json)
        assert payload is not None
        assert len(payload.modifications) == 2

        results = execute_modifications(payload, str(tmp_path))
        assert all(r.success for r in results)

        assert (tmp_path / "new.ts").read_text() == "export const x = 1;\n"
        assert "BETA" in (tmp_path / "old.py").read_text()

    @pytest.mark.skipif(
        not importlib.util.find_spec("aurarouter"),
        reason="aurarouter not installed",
    )
    def test_schema_conforms_to_parser_expectations(self):
        """Verify MODIFICATIONS_SCHEMA fields match what parse_artifact_payload expects."""
        from aurarouter.fabric import MODIFICATIONS_SCHEMA

        # Schema requires "modifications" array
        assert "modifications" in MODIFICATIONS_SCHEMA["properties"]
        assert "modifications" in MODIFICATIONS_SCHEMA["required"]

        # Each item requires file_path, modification_type, content, language
        item_schema = MODIFICATIONS_SCHEMA["properties"]["modifications"]["items"]
        assert set(item_schema["required"]) == {
            "file_path",
            "modification_type",
            "content",
            "language",
        }

        # modification_type enum matches what the executor understands
        mod_type_enum = item_schema["properties"]["modification_type"]["enum"]
        assert "full_rewrite" in mod_type_enum
        assert "unified_diff" in mod_type_enum


# ===================================================================
# T7.5: Cross-Component Smoke Tests (AuraCode side)
# ===================================================================


class TestSmokeHappyPath:
    """Chat intent -> no schema enforcement, no artifact parsing."""

    async def test_chat_no_artifacts(self, tmp_path):
        mocks = _build_mock_aurarouter("Here is a helpful explanation.")
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
                files=[FileContext(path="readme.md", language=None)],
            )
            result = await backend.route(
                prompt="What is Python?",
                intent=RequestIntent.CHAT,
                context=ctx,
            )

            # No artifact execution for chat
            assert "artifact_execution" not in result.metadata
            assert result.content == "Here is a helpful explanation."

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)


class TestSmokeEditPath:
    """Edit intent -> schema enforced, JSON returned, artifacts parsed."""

    async def test_edit_writes_file(self, tmp_path):
        artifact_json = _make_modifications_json(
            ("output.py", "full_rewrite", "# generated\nprint('ok')\n", "python"),
        )
        mocks = _build_mock_aurarouter(artifact_json)
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
                files=[FileContext(path="input.py", content="old", language="python")],
            )
            result = await backend.route(
                prompt="rewrite the code",
                intent=RequestIntent.EDIT_CODE,
                context=ctx,
            )

            # File should be written
            assert (tmp_path / "output.py").exists()
            assert "# generated" in (tmp_path / "output.py").read_text()

            # Metadata
            assert "artifact_execution" in result.metadata
            assert result.metadata["artifact_execution"][0]["ok"] is True
            assert "execution_trace" in result.metadata

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)


class TestSmokeFallbackPath:
    """Non-JSON response from fabric -> no crash, standard text return."""

    async def test_plain_text_no_crash(self, tmp_path):
        mocks = _build_mock_aurarouter("Here is your code: def foo(): pass")
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
            )
            result = await backend.route(
                prompt="write code",
                intent=RequestIntent.GENERATE_CODE,
                context=ctx,
            )

            assert result.content == "Here is your code: def foo(): pass"
            # No artifact_execution for plain text
            assert "artifact_execution" not in result.metadata

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)


class TestSmokeNoContext:
    """No context, no routing hints -> baseline pipeline unchanged."""

    async def test_no_context_route(self):
        mocks = _build_mock_aurarouter("response text")
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()

            result = await backend.route(
                prompt="hello",
                intent=RequestIntent.CHAT,
            )

            opts = backend._last_route_options
            assert opts["intent"] == "chat"
            assert opts["routing_hints"] == []
            assert opts["file_constraints"] == []
            assert result.content == "response text"

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)


class TestTraceCompleteness:
    """Verify execution_trace is coherent across all paths."""

    async def test_edit_trace_has_executor_entries(self, tmp_path):
        artifact_json = _make_modifications_json(
            ("a.py", "full_rewrite", "# a\n", "python"),
            ("b.py", "full_rewrite", "# b\n", "python"),
        )
        mocks = _build_mock_aurarouter(artifact_json)
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()

            ctx = SessionContext(
                session_id="s1",
                working_directory=str(tmp_path),
            )
            result = await backend.route(
                prompt="write files",
                intent=RequestIntent.EDIT_CODE,
                context=ctx,
            )

            trace = result.metadata.get("execution_trace", [])
            assert len(trace) >= 2  # at least one entry per file
            assert any("a.py" in t for t in trace)
            assert any("b.py" in t for t in trace)
            assert all("Executor:" in t for t in trace)

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)

    async def test_chat_no_trace(self):
        """Chat intent should not produce execution_trace."""
        mocks = _build_mock_aurarouter("just text")
        originals = {}
        keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
        for key in keys:
            originals[key] = sys.modules.get(key)
        sys.modules.update({k: v for k, v in mocks.items() if k.startswith("aurarouter")})

        try:
            cls = _get_backend_cls()
            backend = cls()

            result = await backend.route(
                prompt="hi",
                intent=RequestIntent.CHAT,
            )

            # No execution_trace for non-actionable intents
            assert "execution_trace" not in result.metadata

        finally:
            for key in keys:
                if originals[key] is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = originals[key]
            import auracode.routing.embedded as mod

            importlib.reload(mod)
