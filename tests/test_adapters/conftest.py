"""Shared fixtures for adapter tests."""

from __future__ import annotations

import pytest

from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    TokenUsage,
)


@pytest.fixture()
def adapter_registry() -> AdapterRegistry:
    """Return a fresh, empty adapter registry."""
    return AdapterRegistry()


@pytest.fixture()
def claude_code_adapter() -> ClaudeCodeAdapter:
    """Return a ClaudeCodeAdapter instance."""
    return ClaudeCodeAdapter()


@pytest.fixture()
def sample_engine_response() -> EngineResponse:
    """Return a realistic EngineResponse with artifacts."""
    return EngineResponse(
        request_id="resp-001",
        content="Here is your code:",
        model_used="claude-sonnet-4-20250514",
        usage=TokenUsage(prompt_tokens=50, completion_tokens=120),
        artifacts=[
            FileArtifact(
                path="src/hello.py",
                content="def hello():\n    print('Hello, world!')\n",
                action="create",
            ),
        ],
    )
