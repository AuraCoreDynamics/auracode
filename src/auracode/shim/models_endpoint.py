"""GET /v1/models — list available models in OpenAI format."""

from __future__ import annotations

import logging

from aiohttp import web

logger = logging.getLogger("AuraCode.Shim")


async def list_models(request: web.Request) -> web.Response:
    """Return models available through the engine's router backend.

    Response follows the OpenAI ``GET /v1/models`` schema::

        {"object": "list", "data": [{"id": "...", "object": "model", ...}]}
    """
    engine = request.app["engine"]

    try:
        models = await engine.router.list_models()
    except Exception as ex:  # noqa: F841
        logger.debug("shim.models_endpoint.list_models_error", exc_info=True)
        models = []

    data = [
        {
            "id": m.model_id,
            "object": "model",
            "created": 0,
            "owned_by": "auracode",
        }
        for m in models
    ]

    return web.json_response({"object": "list", "data": data})
