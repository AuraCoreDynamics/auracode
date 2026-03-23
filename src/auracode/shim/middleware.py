"""Middleware for the shim server — error handling, logging, CORS."""

from __future__ import annotations

import json
import traceback

import structlog
from aiohttp import web

log = structlog.get_logger()


@web.middleware
async def error_middleware(request: web.Request, handler) -> web.StreamResponse:
    """Catch unhandled exceptions and return OpenAI-style error JSON."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except json.JSONDecodeError:
        return web.json_response(
            {
                "error": {
                    "message": "Invalid JSON in request body.",
                    "type": "invalid_request_error",
                    "code": "invalid_json",
                }
            },
            status=400,
        )
    except Exception as exc:
        log.error("shim.unhandled_error", error=str(exc), tb=traceback.format_exc())
        return web.json_response(
            {
                "error": {
                    "message": f"Internal server error: {exc}",
                    "type": "server_error",
                    "code": "internal_error",
                }
            },
            status=500,
        )


@web.middleware
async def logging_middleware(request: web.Request, handler) -> web.StreamResponse:
    """Log every incoming request."""
    log.info("shim.request", method=request.method, path=request.path)
    response = await handler(request)
    log.info(
        "shim.response",
        method=request.method,
        path=request.path,
        status=response.status,
    )
    return response


async def cors_handler(request: web.Request) -> web.Response:
    """Handle CORS preflight requests."""
    return web.Response(
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }
    )
