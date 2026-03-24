"""MCP tool catalog client for querying AuraRouter's MCP registry."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolInfo(BaseModel):
    """Descriptor for a single MCP tool."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any] = {}


class McpCatalogClient:
    """Queries AuraRouter's MCP tool catalog.

    Wraps :class:`aurarouter.mcp_client.registry.McpClientRegistry` to expose
    an async interface consumable by AuraCode.  The *config_loader* argument
    is an optional :class:`aurarouter.config.ConfigLoader` used for model
    syncing.
    """

    def __init__(
        self,
        registry: Any | None = None,
        config_loader: Any | None = None,
    ) -> None:
        self._registry = registry
        self._config = config_loader

    async def list_tools(self) -> list[ToolInfo]:
        """Return all tools from connected MCP clients."""
        if self._registry is None:
            return []

        raw_tools: list[dict] = await asyncio.to_thread(
            self._registry.get_all_remote_tools,
        )
        tools: list[ToolInfo] = []
        for t in raw_tools:
            tools.append(
                ToolInfo(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema", t.get("input_schema", {})),
                )
            )
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool by name on the first client that owns it.

        Raises ``ValueError`` if no client exposes the requested tool.
        """
        if self._registry is None:
            raise ValueError("No MCP registry configured")

        clients: dict = await asyncio.to_thread(self._registry.get_clients)
        for _name, client in clients.items():
            client_tools = client.get_tools()
            for t in client_tools:
                if t.get("name") == tool_name:
                    result = await asyncio.to_thread(client.call_tool, tool_name, arguments)
                    return result

        raise ValueError(f"Tool '{tool_name}' not found in any MCP client")
