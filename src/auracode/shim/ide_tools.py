"""Tool execution framework for IDE WebSocket integration."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Literal

import structlog

from auracode.shim.ide_protocol import ToolRequest

log = structlog.get_logger()


class ToolManager:
    """Manages pending tool requests sent to the IDE for confirmation.

    Each tool request gets a unique ID and an associated
    :class:`asyncio.Future` that resolves when the IDE responds.
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    @property
    def pending_count(self) -> int:
        """Number of unresolved tool requests."""
        return len(self._pending)

    async def request_tool(
        self,
        ws,
        tool: Literal["file_write", "file_read", "terminal_exec", "search"],
        params: dict[str, Any],
        description: str = "",
    ) -> dict[str, Any]:
        """Send a tool request to the IDE and wait for the response.

        Parameters
        ----------
        ws:
            The aiohttp WebSocket response object.
        tool:
            The tool type to request.
        params:
            Tool-specific parameters (e.g. path, content for file_write).
        description:
            Human-readable description of the operation.

        Returns
        -------
        dict
            ``{"approved": bool, "result": str, "error": str | None}``
        """
        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future

        msg = ToolRequest(
            request_id=request_id,
            tool=tool,
            params=params,
            description=description,
        )

        log.debug("ide_tools.request", request_id=request_id, tool=tool)
        await ws.send_json(msg.model_dump())

        try:
            return await future
        finally:
            self._pending.pop(request_id, None)

    def resolve_tool(
        self,
        request_id: str,
        approved: bool,
        result: str = "",
        error: str | None = None,
    ) -> bool:
        """Resolve a pending tool request future.

        Returns True if the request_id was found and resolved, False
        otherwise.
        """
        future = self._pending.get(request_id)
        if future is None or future.done():
            log.warning("ide_tools.resolve_unknown", request_id=request_id)
            return False

        future.set_result({"approved": approved, "result": result, "error": error})
        log.debug("ide_tools.resolved", request_id=request_id, approved=approved)
        return True

    def cancel_all(self) -> None:
        """Cancel all pending tool futures (e.g. on client disconnect)."""
        for request_id, future in list(self._pending.items()):
            if not future.done():
                future.cancel()
        self._pending.clear()
