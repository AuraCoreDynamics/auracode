"""Tests for adapter discovery."""

from __future__ import annotations

from auracode.adapters.loader import discover_adapters
from auracode.engine.registry import AdapterRegistry


class TestDiscoverAdapters:
    """discover_adapters should find real adapters and tolerate stubs."""

    def test_discovers_claude_code(self, adapter_registry: AdapterRegistry) -> None:
        discover_adapters(adapter_registry)
        assert "claude-code" in adapter_registry.list_adapters()

    def test_skeletons_do_not_register(self, adapter_registry: AdapterRegistry) -> None:
        discover_adapters(adapter_registry)
        adapters = adapter_registry.list_adapters()
        assert "copilot" not in adapters
        assert "aider" not in adapters
        assert "codestral" not in adapters

    def test_discovery_does_not_crash(self, adapter_registry: AdapterRegistry) -> None:
        """Even if a subpackage is broken, discovery should complete."""
        # This simply verifies that the function returns without exception.
        discover_adapters(adapter_registry)

    def test_registered_adapter_is_retrievable(self, adapter_registry: AdapterRegistry) -> None:
        discover_adapters(adapter_registry)
        adapter = adapter_registry.get("claude-code")
        assert adapter is not None
        assert adapter.name == "claude-code"
