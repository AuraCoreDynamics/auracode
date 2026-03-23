"""Tests for GET /v1/models endpoint."""

from __future__ import annotations


async def test_list_models(client):
    """GET /v1/models returns a valid model list."""
    resp = await client.get("/v1/models")
    assert resp.status == 200
    body = await resp.json()

    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 2

    model = body["data"][0]
    assert model["id"] == "mock-model-v1"
    assert model["object"] == "model"
    assert model["owned_by"] == "auracode"
    assert "created" in model
