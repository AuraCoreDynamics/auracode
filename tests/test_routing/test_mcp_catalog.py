"""Tests for the MCP catalog client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from auracode.routing.mcp_catalog import McpCatalogClient, ToolInfo


class TestListTools:
    async def test_list_tools_returns_tool_info(self, mock_registry):
        client = McpCatalogClient(registry=mock_registry)
        tools = await client.list_tools()

        assert len(tools) == 2
        assert all(isinstance(t, ToolInfo) for t in tools)
        assert tools[0].name == "read_file"
        assert tools[0].description == "Read file contents"
        assert tools[0].input_schema["type"] == "object"
        assert tools[1].name == "run_command"

    async def test_list_tools_no_registry(self):
        client = McpCatalogClient()
        tools = await client.list_tools()
        assert tools == []

    async def test_list_tools_empty_registry(self):
        registry = MagicMock()
        registry.get_all_remote_tools = MagicMock(return_value=[])
        client = McpCatalogClient(registry=registry)
        tools = await client.list_tools()
        assert tools == []


class TestCallTool:
    async def test_call_tool_delegates(self, mock_registry):
        client = McpCatalogClient(registry=mock_registry)
        result = await client.call_tool("read_file", {"path": "/tmp/x"})

        assert result == {"ok": True}
        mock_registry._mock_client.call_tool.assert_called_once_with(
            "read_file", {"path": "/tmp/x"}
        )

    async def test_call_tool_not_found(self, mock_registry):
        client = McpCatalogClient(registry=mock_registry)
        with pytest.raises(ValueError, match="not found"):
            await client.call_tool("nonexistent_tool", {})

    async def test_call_tool_no_registry(self):
        client = McpCatalogClient()
        with pytest.raises(ValueError, match="No MCP registry"):
            await client.call_tool("anything", {})


class TestToolInfoModel:
    def test_frozen(self):
        info = ToolInfo(name="t", description="d")
        with pytest.raises(Exception):
            info.name = "other"  # type: ignore[misc]

    def test_default_schema(self):
        info = ToolInfo(name="t", description="d")
        assert info.input_schema == {}
