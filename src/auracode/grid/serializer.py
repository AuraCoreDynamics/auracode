"""Converts between AuraCode domain models and grid messages."""

from __future__ import annotations

from typing import Any

from auracode.grid.messages import GridRequest, GridResponse
from auracode.models.context import SessionContext
from auracode.models.request import RequestIntent, TokenUsage
from auracode.routing.base import RouteResult


def engine_request_to_grid(
    request_id: str,
    prompt: str,
    intent: RequestIntent,
    context: SessionContext | None = None,
    options: dict[str, Any] | None = None,
) -> GridRequest:
    """Build a :class:`GridRequest` from AuraCode domain objects."""
    context_json = ""
    if context is not None:
        context_json = context.model_dump_json()

    str_options: dict[str, str] = {}
    if options:
        str_options = {k: str(v) for k, v in options.items()}

    return GridRequest(
        request_id=request_id,
        intent=intent.value,
        prompt=prompt,
        context_json=context_json,
        options=str_options,
    )


def grid_response_to_route_result(response: GridResponse) -> RouteResult:
    """Convert a :class:`GridResponse` into a :class:`RouteResult`."""
    usage = TokenUsage(
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
    )
    return RouteResult(
        content=response.content,
        model_used=response.model_used,
        usage=usage,
    )
