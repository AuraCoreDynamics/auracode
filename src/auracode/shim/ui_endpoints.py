"""Mission Command UI REST and WebSocket endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from auracode.git.conflict_resolver import ConflictMarkerParser, MergeConflictResolver

logger = logging.getLogger(__name__)


async def events_websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Stream live telemetry events from MissionEventBus over WebSocket."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    engine = request.app.get("engine")
    event_bus = getattr(engine, "event_bus", None)

    if not event_bus:
        await ws.send_json(
            {"type": "system.notice", "payload": {"message": "MissionEventBus not initialized."}}
        )
        await ws.close()
        return ws

    # Send recent historical events for immediate client hydration
    recent_events = event_bus.get_recent_events(limit=50)
    for evt in recent_events:
        await ws.send_str(json.dumps(evt))

    async def _stream_events() -> None:
        try:
            async for evt in event_bus.subscribe():
                if ws.closed:
                    break
                await ws.send_str(json.dumps(evt))
        except (asyncio.CancelledError, ConnectionResetError):
            pass
        except Exception as exc:
            logger.debug(f"Event streaming error: {exc}")

    stream_task = asyncio.create_task(_stream_events())

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                # Echo ping or command messages if needed
                if msg.data == "ping":
                    await ws.send_str(json.dumps({"type": "pong"}))
            elif msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.ERROR):
                break
    finally:
        stream_task.cancel()
        try:
            await stream_task
        except asyncio.CancelledError:
            pass

    return ws


async def fleet_workspaces_handler(request: web.Request) -> web.Response:
    """Manage and list multi-workspace fleet (GET, POST, DELETE)."""
    from auracode.engine.fleet_manager import FleetWorkspaceManager

    fleet_mgr: FleetWorkspaceManager = request.app.setdefault(
        "fleet_manager", FleetWorkspaceManager()
    )

    if request.method == "POST":
        try:
            body = await request.json()
            target_path = body.get("path")
            if not target_path:
                return web.json_response({"error": "Missing 'path' parameter"}, status=400)
            res = fleet_mgr.register(target_path)
            return web.json_response({"success": True, "workspace": res})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)

    if request.method == "DELETE":
        try:
            body = await request.json()
            target_path = body.get("path")
            if not target_path:
                return web.json_response({"error": "Missing 'path' parameter"}, status=400)
            ok = fleet_mgr.unregister(target_path)
            return web.json_response({"success": ok})
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)

    workspaces = await fleet_mgr.list_workspaces()
    return web.json_response({"workspaces": workspaces})


async def fleet_conflicts_get_handler(request: web.Request) -> web.Response:
    """GET /api/fleet/conflicts — scan for files with active merge conflicts."""
    workspace_param = request.query.get("workspace", ".")
    root_p = Path(workspace_param).resolve()
    conflicted_paths = ConflictMarkerParser.find_conflicted_files(str(root_p))

    conflicts_data = []
    for p in conflicted_paths:
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            blocks = ConflictMarkerParser.parse_text(content)
            conflicts_data.append(
                {
                    "file": str(p),
                    "relative_file": str(p.relative_to(root_p)),
                    "block_count": len(blocks),
                    "blocks": [
                        {
                            "start_line": b.start_line,
                            "end_line": b.end_line,
                            "ours_label": b.ours_label,
                            "ours_content": b.ours_content,
                            "theirs_label": b.theirs_label,
                            "theirs_content": b.theirs_content,
                            "base_content": b.base_content,
                        }
                        for b in blocks
                    ],
                }
            )
        except Exception as exc:
            logger.debug(f"Error parsing conflict in {p}: {exc}")

    return web.json_response({"conflicts": conflicts_data})


async def fleet_conflicts_resolve_handler(request: web.Request) -> web.Response:
    """POST /api/fleet/conflicts — resolve merge conflicts via AI synthesizer."""
    engine = request.app.get("engine")
    if not engine:
        return web.json_response({"error": "Engine not initialized"}, status=500)

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    target_file = body.get("file")
    resolve_all = body.get("all", False)

    journal = getattr(engine, "_journal", None)
    resolver = MergeConflictResolver(engine, journal=journal)

    if target_file:
        success, msg = await resolver.resolve_file(target_file)
        return web.json_response(
            {"success": success, "message": msg, "resolved_count": 1 if success else 0}
        )

    if resolve_all:
        conflicted = ConflictMarkerParser.find_conflicted_files(".")
        resolved_count = 0
        messages = []
        for p in conflicted:
            ok, msg = await resolver.resolve_file(p)
            if ok:
                resolved_count += 1
            messages.append(f"{p.name}: {msg}")
        return web.json_response(
            {
                "success": resolved_count > 0 or not conflicted,
                "resolved_count": resolved_count,
                "total_conflicted": len(conflicted),
                "messages": messages,
            }
        )

    return web.json_response({"error": "Must specify 'file' or 'all': true"}, status=400)


async def fleet_rollback_handler(request: web.Request) -> web.Response:
    """POST /api/fleet/rollback — trigger rollback to latest or specified snapshot."""
    engine = request.app.get("engine")
    journal = getattr(engine, "_journal", None)
    if not journal:
        return web.json_response({"error": "File journal not available"}, status=500)

    snapshot_id: str | None = None
    try:
        if request.can_read_body:
            body: dict[str, Any] = await request.json()
            snapshot_id = body.get("snapshot_id")
    except Exception:
        pass

    if not snapshot_id:
        if journal.snapshots:
            snapshot_id = list(journal.snapshots.keys())[-1]
        else:
            return web.json_response(
                {"success": False, "message": "No snapshots recorded to roll back."},
                status=200,
            )

    try:
        restored = journal.rollback_snapshot(snapshot_id)
    except KeyError:
        return web.json_response(
            {"success": False, "message": f"Snapshot ID not found: {snapshot_id}"},
            status=404,
        )

    event_bus = getattr(engine, "event_bus", None)
    if event_bus:
        event_bus.broadcast(
            "journal.rollback_executed",
            {"snapshot_id": snapshot_id, "restored_count": len(restored)},
        )

    return web.json_response(
        {
            "success": True,
            "snapshot_id": snapshot_id,
            "restored_count": len(restored),
            "restored_files": restored,
        }
    )


async def ui_static_handler(request: web.Request) -> web.StreamResponse:
    """Serve static web assets for Mission Command Flight Deck."""
    tail = request.match_info.get("tail", "")
    assets_dir = (Path(__file__).parent.parent / "assets" / "ui").resolve()

    if not tail or tail == "/":
        target = (assets_dir / "index.html").resolve()
    else:
        target = (assets_dir / tail.lstrip("/")).resolve()

    # Prevent directory traversal outside assets/ui
    try:
        if not target.is_relative_to(assets_dir):
            return web.Response(status=403, text="Forbidden")
    except ValueError:
        return web.Response(status=403, text="Forbidden")

    if not target.is_file():
        target = assets_dir / "index.html"

    if not target.is_file():
        return web.Response(
            status=404,
            text="Mission Command UI assets not found. Run installer or check MANIFEST.in.",
            content_type="text/plain",
        )

    content_types = {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
    }
    ctype = content_types.get(target.suffix, "application/octet-stream")
    return web.FileResponse(target, headers={"Content-Type": ctype})
