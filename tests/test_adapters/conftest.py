"""Shared fixtures for adapter tests."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from auracode.adapters.claude_code.adapter import ClaudeCodeAdapter
from auracode.engine.registry import AdapterRegistry
from auracode.models.request import (
    EngineResponse,
    FileArtifact,
    TokenUsage,
)


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Reset structlog to use stderr so adapter discovery logging works."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
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


@pytest.fixture()
def mock_create_application():
    """Mock create_application to return a stub engine and adapter registry.

    The stub engine returns a fixed EngineResponse with content "mock response".
    The adapter registry contains a real ClaudeCodeAdapter.
    """
    mock_response = EngineResponse(
        request_id="mock-001",
        content="mock response",
        model_used="mock-model",
    )

    mock_engine = MagicMock()
    mock_engine.execute = AsyncMock(return_value=mock_response)

    adapter_reg = AdapterRegistry()
    adapter_reg.register(ClaudeCodeAdapter())

    mock_backend_reg = MagicMock()
    mock_prefs = MagicMock()

    with patch(
        "auracode.app.create_application",
        return_value=(mock_engine, adapter_reg, mock_backend_reg, mock_prefs),
    ) as mock_fn:
        yield mock_fn
