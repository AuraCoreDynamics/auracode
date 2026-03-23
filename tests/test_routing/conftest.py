"""Mock fixtures for AuraRouter dependencies.

All AuraRouter classes are mocked so tests run without AuraRouter installed.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Synthetic aurarouter package — inserted into sys.modules so that
# ``from aurarouter.config import ConfigLoader`` etc. resolve to mocks.
# ---------------------------------------------------------------------------

def _build_mock_config_loader(config: dict | None = None) -> MagicMock:
    """Create a mock that behaves like ``aurarouter.config.ConfigLoader``."""
    cfg = config or {
        "models": {
            "local-coder": {"provider": "ollama", "tags": ["local"]},
            "cloud-reasoning": {"provider": "gemini", "tags": ["cloud"]},
        },
        "roles": {
            "coder": ["local-coder"],
            "reasoning": ["cloud-reasoning"],
        },
    }
    loader = MagicMock()
    loader.config = cfg
    loader.get_role_chain = MagicMock(
        side_effect=lambda role: list(cfg.get("roles", {}).get(role, []))
    )
    loader.get_model_config = MagicMock(
        side_effect=lambda mid: dict(cfg.get("models", {}).get(mid, {}))
    )
    loader.get_all_model_ids = MagicMock(
        return_value=list(cfg.get("models", {}).keys())
    )
    loader.get_all_roles = MagicMock(
        return_value=list(cfg.get("roles", {}).keys())
    )
    return loader


def _build_mock_fabric(default_response: str = "generated code") -> MagicMock:
    """Create a mock that behaves like ``aurarouter.fabric.ComputeFabric``."""
    fabric = MagicMock()
    fabric.execute = MagicMock(return_value=default_response)
    return fabric


@pytest.fixture()
def mock_config_loader() -> MagicMock:
    return _build_mock_config_loader()


@pytest.fixture()
def mock_fabric() -> MagicMock:
    return _build_mock_fabric()


@pytest.fixture()
def _patch_aurarouter(mock_config_loader, mock_fabric):
    """Inject fake ``aurarouter`` modules into ``sys.modules``.

    This allows ``from aurarouter.config import ConfigLoader`` to resolve
    without the real package installed.  The fixture yields the mocks and
    cleans up afterwards.
    """
    # Build a minimal module hierarchy.
    ar = ModuleType("aurarouter")
    ar_config = ModuleType("aurarouter.config")
    ar_fabric = ModuleType("aurarouter.fabric")

    # ConfigLoader *class* — when instantiated returns our mock.
    config_cls = MagicMock(return_value=mock_config_loader)
    ar_config.ConfigLoader = config_cls  # type: ignore[attr-defined]

    # ComputeFabric *class* — when instantiated returns our mock.
    fabric_cls = MagicMock(return_value=mock_fabric)
    ar_fabric.ComputeFabric = fabric_cls  # type: ignore[attr-defined]

    originals: dict[str, ModuleType | None] = {}
    keys = ["aurarouter", "aurarouter.config", "aurarouter.fabric"]
    for key in keys:
        originals[key] = sys.modules.get(key)
        # Remove any cached real module first.
    sys.modules["aurarouter"] = ar
    sys.modules["aurarouter.config"] = ar_config
    sys.modules["aurarouter.fabric"] = ar_fabric

    yield {
        "config_cls": config_cls,
        "fabric_cls": fabric_cls,
        "config_loader": mock_config_loader,
        "fabric": mock_fabric,
    }

    # Restore original state.
    for key in keys:
        if originals[key] is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = originals[key]


@pytest.fixture()
def mock_registry() -> MagicMock:
    """Mock for ``aurarouter.mcp_client.registry.McpClientRegistry``."""
    registry = MagicMock()
    registry.get_all_remote_tools = MagicMock(return_value=[
        {
            "name": "read_file",
            "description": "Read file contents",
            "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
            "_source_client": "grid-node-1",
        },
        {
            "name": "run_command",
            "description": "Execute a shell command",
            "inputSchema": {},
            "_source_client": "grid-node-1",
        },
    ])

    # Build a mock client that owns the tools.
    mock_client = MagicMock()
    mock_client.get_tools.return_value = [
        {"name": "read_file"},
        {"name": "run_command"},
    ]
    mock_client.call_tool = MagicMock(return_value={"ok": True})

    registry.get_clients = MagicMock(return_value={"grid-node-1": mock_client})
    registry._mock_client = mock_client  # exposed for assertions
    return registry
