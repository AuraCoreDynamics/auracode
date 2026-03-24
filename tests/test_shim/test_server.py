"""Tests for server creation and health endpoint."""

from __future__ import annotations

from aiohttp import web

from auracode.shim.server import create_app


def test_create_app_returns_application(mock_engine):
    """create_app() produces an aiohttp Application."""
    app = create_app(mock_engine)
    assert isinstance(app, web.Application)
    assert app["engine"] is mock_engine


def test_create_app_has_routes(mock_engine):
    """All expected routes are registered."""
    app = create_app(mock_engine)
    routes = {
        r.resource.canonical for r in app.router.routes() if hasattr(r, "resource") and r.resource
    }
    assert "/v1/chat/completions" in routes
    assert "/v1/completions" in routes
    assert "/v1/models" in routes
    assert "/health" in routes


async def test_health_endpoint(client):
    """GET /health returns 200 with status ok."""
    resp = await client.get("/health")
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "ok"
