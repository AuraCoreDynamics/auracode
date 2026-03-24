"""WebSocket handler for IDE integration."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from aiohttp import WSMsgType, web

from auracode.models.context import FileContext, SessionContext
from auracode.models.request import EngineRequest, RequestIntent
from auracode.shim.ide_protocol import (
    CancelRequest,
    ChatMessage,
    ServerError,
    StatusUpdate,
    StreamEnd,
    StreamToken,
    ToolResponse,
)
from auracode.shim.ide_tools import ToolManager

log = structlog.get_logger()

# Maps session_id → ToolManager so tools survive across messages.
_tool_managers: dict[str, ToolManager] = {}

# Maps request_id → asyncio.Event for cancellation.
_cancel_flags: dict[str, asyncio.Event] = {}


def _get_tool_manager(session_id: str) -> ToolManager:
    """Get or create a ToolManager for the given session."""
    if session_id not in _tool_managers:
        _tool_managers[session_id] = ToolManager()
    return _tool_managers[session_id]


def _map_intent(raw: str | None) -> RequestIntent:
    """Convert a string intent from the IDE to a RequestIntent enum."""
    if raw is None:
        return RequestIntent.CHAT
    try:
        return RequestIntent(raw)
    except ValueError:
        return RequestIntent.CHAT


def _build_context(msg: ChatMessage, session_id: str) -> SessionContext:
    """Build a SessionContext from the IDE context."""
    files: list[FileContext] = []
    if msg.ide_context:
        for f in msg.ide_context.open_files:
            files.append(
                FileContext(
                    path=f.path,
                    content=f.content,
                    language=f.language,
                )
            )

    return SessionContext(
        session_id=session_id,
        working_directory=msg.ide_context.workspace_root if msg.ide_context else ".",
        files=files,
    )


async def handle_chat(ws: web.WebSocketResponse, data: dict, engine) -> None:
    """Validate a ChatMessage, build EngineRequest, stream tokens, send StreamEnd."""
    try:
        msg = ChatMessage.model_validate(data)
    except Exception as exc:
        err = ServerError(message=f"Invalid chat message: {exc}", code="invalid_message")
        await ws.send_json(err.model_dump())
        return

    request_id = uuid.uuid4().hex
    session_id = msg.session_id or uuid.uuid4().hex
    intent = _map_intent(msg.intent)
    context = _build_context(msg, session_id)

    engine_request = EngineRequest(
        request_id=request_id,
        intent=intent,
        prompt=msg.message,
        context=context,
        adapter_name="ide-websocket",
    )

    # Set up cancellation flag.
    cancel_event = asyncio.Event()
    _cancel_flags[request_id] = cancel_event

    # Send status.
    status = StatusUpdate(
        request_id=request_id,
        message="Generating response...",
        phase="streaming",
    )
    await ws.send_json(status.model_dump())

    model_used: str | None = None
    try:
        async for chunk in engine.execute_stream(engine_request):
            # Check for cancellation between yields.
            if cancel_event.is_set():
                log.info("ide_ws.cancelled", request_id=request_id)
                break

            token = StreamToken(
                request_id=request_id,
                content=chunk,
                model_used=model_used,
            )
            await ws.send_json(token.model_dump())
    except Exception as exc:
        log.error("ide_ws.stream_error", request_id=request_id, error=str(exc))
        err = ServerError(
            request_id=request_id,
            message=str(exc),
            code="stream_error",
        )
        await ws.send_json(err.model_dump())
    finally:
        _cancel_flags.pop(request_id, None)

    end = StreamEnd(
        request_id=request_id,
        model_used=model_used,
    )
    await ws.send_json(end.model_dump())


def handle_cancel(data: dict) -> None:
    """Set the cancellation flag for an in-progress request."""
    try:
        cancel = CancelRequest.model_validate(data)
    except Exception:
        return
    event = _cancel_flags.get(cancel.request_id)
    if event is not None:
        event.set()
        log.info("ide_ws.cancel_set", request_id=cancel.request_id)


def handle_tool_response(data: dict) -> None:
    """Resolve a pending tool future from an IDE tool response."""
    try:
        resp = ToolResponse.model_validate(data)
    except Exception:
        return

    # Find the tool manager that owns this request.
    for tm in _tool_managers.values():
        if tm.resolve_tool(resp.request_id, resp.approved, resp.result, resp.error):
            return
    log.warning("ide_ws.tool_response_orphan", request_id=resp.request_id)


async def ide_websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Accept a WebSocket connection and dispatch on message type.

    Route: GET /ws/ide

    Chat messages are dispatched as background tasks so that cancel and
    tool_response messages can be processed while streaming is in progress.
    """
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    engine = request.app["engine"]
    log.info("ide_ws.connected")

    # Track background chat tasks for cleanup.
    chat_tasks: set[asyncio.Task] = set()

    try:
        async for raw_msg in ws:
            if raw_msg.type == WSMsgType.TEXT:
                try:
                    data = raw_msg.json()
                except Exception:
                    err = ServerError(message="Invalid JSON", code="invalid_json")
                    await ws.send_json(err.model_dump())
                    continue

                msg_type = data.get("type")

                if msg_type == "chat":
                    # Run chat handler as a background task so the message
                    # loop remains free to process cancel/tool_response.
                    task = asyncio.create_task(handle_chat(ws, data, engine))
                    chat_tasks.add(task)
                    task.add_done_callback(chat_tasks.discard)
                elif msg_type == "cancel":
                    handle_cancel(data)
                elif msg_type == "tool_response":
                    handle_tool_response(data)
                else:
                    err = ServerError(
                        message=f"Unknown message type: {msg_type}",
                        code="unknown_type",
                    )
                    await ws.send_json(err.model_dump())

            elif raw_msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSING):
                break
    except Exception as exc:
        log.error("ide_ws.error", error=str(exc))
    finally:
        # Cancel any in-flight chat tasks on disconnect.
        for task in chat_tasks:
            task.cancel()
        if chat_tasks:
            await asyncio.gather(*chat_tasks, return_exceptions=True)
        log.info("ide_ws.disconnected")
        # Clean up — do not remove tool managers (session persists).

    return ws


async def status_handler(request: web.Request) -> web.Response:
    """GET /api/status — return server status."""
    engine = request.app["engine"]
    healthy = await engine.router.health_check() if hasattr(engine, "router") else False
    return web.json_response(
        {
            "status": "ok" if healthy else "degraded",
            "sessions": len(engine.session_manager._sessions)
            if hasattr(engine, "session_manager")
            else 0,
            "pending_tools": sum(tm.pending_count for tm in _tool_managers.values()),
        }
    )


async def session_handler(request: web.Request) -> web.Response:
    """GET /api/session/{id} — return session info."""
    session_id = request.match_info["id"]
    engine = request.app["engine"]
    session = engine.get_session(session_id)
    if session is None:
        return web.json_response({"error": "Session not found"}, status=404)
    return web.json_response(
        {
            "session_id": session.session_id,
            "working_directory": session.working_directory,
            "history_length": len(session.history),
            "files": [f.path for f in session.files],
        }
    )


async def clear_session(request: web.Request) -> web.Response:
    """DELETE /api/session/{id} — close and discard a session."""
    session_id = request.match_info["id"]
    engine = request.app["engine"]
    engine.close_session(session_id)
    # Also clean up tool manager for the session.
    tm = _tool_managers.pop(session_id, None)
    if tm is not None:
        tm.cancel_all()
    return web.json_response({"status": "closed", "session_id": session_id})
