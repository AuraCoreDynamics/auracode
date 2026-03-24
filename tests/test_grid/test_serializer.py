"""Tests for grid message serialization round-trips."""

from __future__ import annotations

import json

from auracode.grid.messages import GridRequest, GridResponse
from auracode.grid.serializer import engine_request_to_grid, grid_response_to_route_result
from auracode.models.context import FileContext, SessionContext
from auracode.models.request import RequestIntent


class TestEngineRequestToGrid:
    def test_basic_conversion(self) -> None:
        req = engine_request_to_grid(
            request_id="abc123",
            prompt="Write hello world",
            intent=RequestIntent.GENERATE_CODE,
        )
        assert isinstance(req, GridRequest)
        assert req.request_id == "abc123"
        assert req.intent == "generate_code"
        assert req.prompt == "Write hello world"
        assert req.context_json == ""
        assert req.options == {}

    def test_with_context(self) -> None:
        ctx = SessionContext(
            session_id="s1",
            working_directory="/tmp",
            files=[FileContext(path="main.py", content="print('hi')")],
        )
        req = engine_request_to_grid(
            request_id="x",
            prompt="explain",
            intent=RequestIntent.EXPLAIN_CODE,
            context=ctx,
        )
        assert req.context_json != ""
        parsed = json.loads(req.context_json)
        assert parsed["session_id"] == "s1"
        assert parsed["files"][0]["path"] == "main.py"

    def test_with_options(self) -> None:
        req = engine_request_to_grid(
            request_id="y",
            prompt="go",
            intent=RequestIntent.CHAT,
            options={"temperature": 0.7, "max_tokens": 1024},
        )
        assert req.options["temperature"] == "0.7"
        assert req.options["max_tokens"] == "1024"

    def test_none_context_and_options(self) -> None:
        req = engine_request_to_grid(
            request_id="z",
            prompt="hi",
            intent=RequestIntent.CHAT,
            context=None,
            options=None,
        )
        assert req.context_json == ""
        assert req.options == {}


class TestGridResponseToRouteResult:
    def test_basic_conversion(self) -> None:
        resp = GridResponse(
            request_id="abc",
            content="Hello World",
            model_used="gpt-4",
            prompt_tokens=10,
            completion_tokens=20,
            error="",
        )
        result = grid_response_to_route_result(resp)
        assert result.content == "Hello World"
        assert result.model_used == "gpt-4"
        assert result.usage is not None
        assert result.usage.prompt_tokens == 10
        assert result.usage.completion_tokens == 20

    def test_zero_tokens(self) -> None:
        resp = GridResponse(content="ok", model_used="m")
        result = grid_response_to_route_result(resp)
        assert result.usage is not None
        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0

    def test_round_trip_preserves_content(self) -> None:
        original_prompt = "def fib(n):\n    pass"
        req = engine_request_to_grid(
            request_id="rt",
            prompt=original_prompt,
            intent=RequestIntent.COMPLETE_CODE,
        )
        assert req.prompt == original_prompt

        resp = GridResponse(
            request_id=req.request_id,
            content="def fib(n):\n    return n if n < 2 else fib(n-1) + fib(n-2)",
            model_used="claude",
            prompt_tokens=15,
            completion_tokens=25,
        )
        result = grid_response_to_route_result(resp)
        assert "fib" in result.content
        assert result.model_used == "claude"
