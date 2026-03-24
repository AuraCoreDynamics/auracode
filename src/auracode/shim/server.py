"""Shim server — aiohttp application factory and launchers."""

from __future__ import annotations

import asyncio
import threading

from aiohttp import web

from auracode.shim.middleware import error_middleware, logging_middleware
from auracode.shim.models_endpoint import list_models
from auracode.shim.openai_compat import chat_completions, completions


async def health_check(request: web.Request) -> web.Response:
    """GET /health — simple liveness check."""
    return web.json_response({"status": "ok"})


def create_app(engine) -> web.Application:
    """Create an aiohttp app wired to the given engine."""
    app = web.Application(middlewares=[error_middleware, logging_middleware])
    app["engine"] = engine

    app.router.add_post("/v1/chat/completions", chat_completions)
    app.router.add_post("/v1/completions", completions)
    app.router.add_get("/v1/models", list_models)
    app.router.add_get("/health", health_check)

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
