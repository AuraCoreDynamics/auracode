"""Tests for domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from auracode.models.config import AuraCodeConfig
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import (
    EngineRequest,
    EngineResponse,
    FileArtifact,
    RequestIntent,
    TokenUsage,
)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestTokenUsage:
    def test_defaults(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_frozen(self) -> None:
        usage = TokenUsage()
        with pytest.raises(ValidationError):
            usage.prompt_tokens = 42  # type: ignore[misc]

    def test_custom_values_and_frozen(self) -> None:
        """Create with custom values, verify both fields, and confirm immutability."""
        usage = TokenUsage(prompt_tokens=150, completion_tokens=300)
        assert usage.prompt_tokens == 150
        assert usage.completion_tokens == 300
        # Verify frozen: both fields must reject assignment
        with pytest.raises(ValidationError):
            usage.prompt_tokens = 999  # type: ignore[misc]
        with pytest.raises(ValidationError):
            usage.completion_tokens = 999  # type: ignore[misc]


class TestFileArtifact:
    def test_create(self) -> None:
        fa = FileArtifact(path="src/main.py", content="print(1)", action="create")
        assert fa.action == "create"

    def test_invalid_action(self) -> None:
        with pytest.raises(ValidationError):
            FileArtifact(path="x", content="y", action="rename")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        fa = FileArtifact(path="a", content="b", action="delete")
        with pytest.raises(ValidationError):
            fa.path = "c"  # type: ignore[misc]


class TestRequestIntent:
    def test_values(self) -> None:
        assert RequestIntent.GENERATE_CODE.value == "generate_code"
        assert RequestIntent("chat") is RequestIntent.CHAT


class TestEngineRequest:
    def test_minimal(self, sample_request: EngineRequest) -> None:
        assert sample_request.request_id == "req-001"
        assert sample_request.intent is RequestIntent.GENERATE_CODE

    def test_frozen(self, sample_request: EngineRequest) -> None:
        with pytest.raises(ValidationError):
            sample_request.prompt = "new"  # type: ignore[misc]


class TestEngineResponse:
    def test_with_error(self) -> None:
        resp = EngineResponse(request_id="r1", content="", error="boom")
        assert resp.error == "boom"

    def test_with_artifacts_full_inspection(self) -> None:
        """Create EngineResponse with artifacts; verify path, content, AND action."""
        artifact = FileArtifact(
            path="src/utils.py",
            content="def add(a, b):\n    return a + b\n",
            action="create",
        )
        resp = EngineResponse(
            request_id="r-art",
            content="Created utility module",
            artifacts=[artifact],
        )
        assert len(resp.artifacts) == 1
        art = resp.artifacts[0]
        assert art.path == "src/utils.py"
        assert "def add(a, b):" in art.content
        assert art.action == "create"
        # Verify the response content is also correct
        assert resp.content == "Created utility module"
        assert resp.request_id == "r-art"


class TestFileContext:
    def test_with_selection(self) -> None:
        fc = FileContext(path="bar.py", selection=(10, 20))
        assert fc.selection == (10, 20)

    def test_minimal_all_fields(self) -> None:
        """Create FileContext with minimal args and check ALL fields."""
        fc = FileContext(path="foo.py")
        assert fc.path == "foo.py"
        assert fc.content is None
        assert fc.language is None
        assert fc.selection is None


class TestSessionContext:
    def test_minimal(self) -> None:
        sc = SessionContext(session_id="s1", working_directory="/tmp")
        assert sc.files == []

    def test_frozen(self) -> None:
        sc = SessionContext(session_id="s1", working_directory="/tmp")
        with pytest.raises(ValidationError):
            sc.session_id = "s2"  # type: ignore[misc]


class TestAuraCodeConfig:
    def test_defaults(self) -> None:
        cfg = AuraCodeConfig()
        assert cfg.default_adapter == "opencode"
        assert cfg.local_context_limit == 100_000

    def test_override(self) -> None:
        cfg = AuraCodeConfig(log_level="DEBUG", grid_endpoint="http://grid:5000")
        assert cfg.log_level == "DEBUG"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerializationRoundTrip:
    def test_engine_request(self, sample_request: EngineRequest) -> None:
        data = sample_request.model_dump()
        restored = EngineRequest.model_validate(data)
        assert restored == sample_request

    def test_engine_response(self, sample_response: EngineResponse) -> None:
        data = sample_response.model_dump()
        restored = EngineResponse.model_validate(data)
        assert restored == sample_response

    def test_session_context(self) -> None:
        ctx = SessionContext(
            session_id="abc",
            working_directory="/w",
            files=[FileContext(path="a.py", content="x")],
            history=[{"role": "user", "content": "hi"}],
            metadata={"key": "val"},
        )
        data = ctx.model_dump()
        restored = SessionContext.model_validate(data)
        assert restored == ctx

    def test_config_json(self) -> None:
        cfg = AuraCodeConfig(adapters={"foo": {"key": "val"}})
        data = cfg.model_dump()
        restored = AuraCodeConfig.model_validate(data)
        assert restored == cfg
