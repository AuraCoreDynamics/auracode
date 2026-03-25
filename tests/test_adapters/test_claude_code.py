"""Tests for the Claude Code adapter, CLI, and formatter."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter
from auracode.adapters.claude_code.cli import claude
from auracode.adapters.claude_code.formatter import format_response
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    RequestIntent,
)

# ---------------------------------------------------------------------------
# Adapter unit tests
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapter:
    def test_name(self, claude_code_adapter: ClaudeCodeAdapter) -> None:
        assert claude_code_adapter.name == "claude-code"

    @pytest.mark.asyncio
    async def test_translate_request_chat(self, claude_code_adapter: ClaudeCodeAdapter) -> None:
        raw = {"prompt": "Hello", "intent": "chat"}
        req = await claude_code_adapter.translate_request(raw)
        assert req.intent == RequestIntent.CHAT
        assert req.prompt == "Hello"
        assert req.adapter_name == "claude-code"
        assert req.request_id  # non-empty UUID string

    @pytest.mark.asyncio
    async def test_translate_request_do(self, claude_code_adapter: ClaudeCodeAdapter) -> None:
        raw = {"prompt": "Write tests", "intent": "do"}
        req = await claude_code_adapter.translate_request(raw)
        assert req.intent == RequestIntent.GENERATE_CODE

    @pytest.mark.asyncio
    async def test_translate_request_explain(self, claude_code_adapter: ClaudeCodeAdapter) -> None:
        raw = {"prompt": "Explain this", "intent": "explain"}
        req = await claude_code_adapter.translate_request(raw)
        assert req.intent == RequestIntent.EXPLAIN_CODE

    @pytest.mark.asyncio
    async def test_translate_request_review(self, claude_code_adapter: ClaudeCodeAdapter) -> None:
        raw = {"prompt": "Review this", "intent": "review"}
        req = await claude_code_adapter.translate_request(raw)
        assert req.intent == RequestIntent.REVIEW

    @pytest.mark.asyncio
    async def test_translate_request_default_intent(
        self,
        claude_code_adapter: ClaudeCodeAdapter,
    ) -> None:
        raw = {"prompt": "Something unknown", "intent": "unknown_thing"}
        req = await claude_code_adapter.translate_request(raw)
        assert req.intent == RequestIntent.CHAT  # falls back to chat

    @pytest.mark.asyncio
    async def test_translate_request_with_options(
        self,
        claude_code_adapter: ClaudeCodeAdapter,
    ) -> None:
        raw = {"prompt": "Hello", "options": {"model": "opus"}}
        req = await claude_code_adapter.translate_request(raw)
        assert req.options == {"model": "opus"}

    @pytest.mark.asyncio
    async def test_translate_request_with_context_files(
        self,
        claude_code_adapter: ClaudeCodeAdapter,
        tmp_path,
    ) -> None:
        test_file = tmp_path / "example.py"
        test_file.write_text("print('hi')", encoding="utf-8")
        raw = {"prompt": "Explain this", "intent": "explain", "context_files": [str(test_file)]}
        req = await claude_code_adapter.translate_request(raw)
        assert req.context is not None
        assert len(req.context.files) == 1
        assert req.context.files[0].content == "print('hi')"
        assert req.context.files[0].language == "py"

    @pytest.mark.asyncio
    async def test_translate_request_type_error(
        self,
        claude_code_adapter: ClaudeCodeAdapter,
    ) -> None:
        with pytest.raises(TypeError):
            await claude_code_adapter.translate_request("not a dict")

    @pytest.mark.asyncio
    async def test_translate_response(
        self,
        claude_code_adapter: ClaudeCodeAdapter,
        sample_engine_response: EngineResponse,
    ) -> None:
        result = await claude_code_adapter.translate_response(sample_engine_response)
        assert "Here is your code:" in result

    def test_get_cli_group(self, claude_code_adapter: ClaudeCodeAdapter) -> None:
        group = claude_code_adapter.get_cli_group()
        assert group is not None
        assert group.name == "claude"


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestFormatter:
    def test_text_mode_content(self, sample_engine_response: EngineResponse) -> None:
        output = format_response(sample_engine_response, json_mode=False)
        assert "Here is your code:" in output
        assert "claude-sonnet" in output
        assert "hello.py" in output

    def test_text_mode_tokens(self, sample_engine_response: EngineResponse) -> None:
        output = format_response(sample_engine_response, json_mode=False)
        assert "50+120=170" in output

    def test_json_mode(self, sample_engine_response: EngineResponse) -> None:
        output = format_response(sample_engine_response, json_mode=True)
        data = json.loads(output)
        assert data["request_id"] == "resp-001"
        assert data["content"] == "Here is your code:"
        assert len(data["artifacts"]) == 1

    def test_error_shown(self) -> None:
        resp = EngineResponse(
            request_id="err-001",
            content="",
            error="something went wrong",
        )
        output = format_response(resp, json_mode=False)
        assert "Error" in output
        assert "something went wrong" in output

    def test_delete_artifact(self) -> None:
        resp = EngineResponse(
            request_id="del-001",
            content="Removed file",
            artifacts=[FileArtifact(path="old.py", content="", action="delete")],
        )
        output = format_response(resp, json_mode=False)
        assert "deleted" in output
        assert "file removed" in output


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestCLI:
    def test_group_has_commands(self) -> None:
        assert "chat" in claude.commands
        assert "do" in claude.commands
        assert "explain" in claude.commands
        assert "review" in claude.commands

    def test_do_command(self, mock_create_application) -> None:
        runner = CliRunner()
        result = runner.invoke(claude, ["do", "write hello world"])
        assert result.exit_code == 0
        assert "mock response" in result.output

    def test_do_command_json_flag(self, mock_create_application) -> None:
        runner = CliRunner()
        result = runner.invoke(claude, ["do", "--json", "write hello"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert "request_id" in data

    def test_explain_command(self, mock_create_application) -> None:
        runner = CliRunner()
        result = runner.invoke(claude, ["explain", "myfile.py"])
        assert result.exit_code == 0
        assert "mock response" in result.output

    def test_review_command(self, mock_create_application) -> None:
        runner = CliRunner()
        result = runner.invoke(claude, ["review", "myfile.py"])
        assert result.exit_code == 0
        assert "mock response" in result.output

    def test_explain_json_flag(self, mock_create_application) -> None:
        runner = CliRunner()
        result = runner.invoke(claude, ["explain", "--json", "myfile.py"])
        assert result.exit_code == 0
        # Extract the JSON portion (may be preceded by a warning for missing files)
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert "request_id" in data

    def test_review_json_flag(self, mock_create_application) -> None:
        runner = CliRunner()
        result = runner.invoke(claude, ["review", "--json", "myfile.py"])
        assert result.exit_code == 0
        # Extract the JSON portion (may be preceded by a warning for missing files)
        json_start = result.output.index("{")
        data = json.loads(result.output[json_start:])
        assert "request_id" in data
