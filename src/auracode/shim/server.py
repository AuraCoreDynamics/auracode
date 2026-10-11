"""Shim server — aiohttp application factory and launchers."""

from __future__ import annotations

import asyncio
import threading

from aiohttp import web

from auracode.shim.ide_websocket import (
    clear_session,
    ide_websocket_handler,
    session_handler,
    status_handler,
)
from auracode.shim.middleware import error_middleware, logging_middleware
from auracode.shim.models_endpoint import list_models
from auracode.shim.openai_compat import chat_completions, completions
from auracode.shim.ui_endpoints import (
    events_websocket_handler,
    fleet_conflicts_get_handler,
    fleet_conflicts_resolve_handler,
    fleet_rollback_handler,
    fleet_workspaces_handler,
    ui_static_handler,
)


async def health_check(request: web.Request) -> web.Response:
    """GET /health — simple liveness check."""
    return web.json_response({"status": "ok"})


@web.middleware
async def token_auth_middleware(request: web.Request, handler):
    """Enforce optional bearer token authentication when auth_token is configured."""
    engine = request.app.get("engine")
    token = getattr(getattr(engine, "config", None), "auth_token", None)
    if token:
        # Exclude public UI static assets and health check
        if not request.path.startswith("/ui") and request.path != "/health":
            auth_header = request.headers.get("Authorization", "")
            if auth_header != f"Bearer {token}" and request.query.get("token") != token:
                return web.json_response({"error": "Unauthorized"}, status=401)
    return await handler(request)


def create_app(engine) -> web.Application:
    """Create an aiohttp app wired to the given engine."""
    app = web.Application(
        middlewares=[error_middleware, logging_middleware, token_auth_middleware],
        client_max_size=10 * 1024 * 1024,  # 10 MB max request body
    )
    app["engine"] = engine

    app.router.add_post("/v1/chat/completions", chat_completions)
    app.router.add_post("/v1/completions", completions)
    app.router.add_get("/v1/models", list_models)
    app.router.add_get("/health", health_check)

    # IDE WebSocket + management endpoints
    app.router.add_get("/ws/ide", ide_websocket_handler)
    app.router.add_get("/api/status", status_handler)
    app.router.add_get("/api/session/{id}", session_handler)
    app.router.add_delete("/api/session/{id}", clear_session)

    # Mission Command Telemetry & Fleet endpoints
    app.router.add_get("/api/events", events_websocket_handler)
    app.router.add_get("/api/fleet/workspaces", fleet_workspaces_handler)
    app.router.add_post("/api/fleet/workspaces", fleet_workspaces_handler)
    app.router.add_delete("/api/fleet/workspaces", fleet_workspaces_handler)
    app.router.add_get("/api/fleet/conflicts", fleet_conflicts_get_handler)
    app.router.add_post("/api/fleet/conflicts", fleet_conflicts_resolve_handler)
    app.router.add_post("/api/fleet/rollback", fleet_rollback_handler)

    # Mission Command UI static flight deck
    app.router.add_get("/ui", ui_static_handler)
    app.router.add_get("/ui/{tail:.*}", ui_static_handler)

    return app


async def start_server(engine, host: str = "127.0.0.1", port: int = 8741) -> None:
    """Start the shim server (blocking)."""
    app = create_app(engine)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    # Block until cancelled.
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


def start_server_daemon(engine, host: str = "127.0.0.1", port: int = 8741) -> threading.Thread:
    """Start the shim server in a daemon thread. Returns the thread."""

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(start_server(engine, host, port))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
