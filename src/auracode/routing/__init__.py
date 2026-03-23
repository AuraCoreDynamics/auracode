"""Routing layer — model selection and dispatch."""

from auracode.routing.base import BaseRouterBackend, ModelInfo, RouteResult
from auracode.routing.intent_map import (
    INTENT_ROLE_MAP,
    build_context_prompt,
    map_intent_to_role,
)
from auracode.routing.mcp_catalog import McpCatalogClient, ToolInfo

__all__ = [
    "BaseRouterBackend",
    "ModelInfo",
    "RouteResult",
    "INTENT_ROLE_MAP",
    "build_context_prompt",
    "map_intent_to_role",
    "McpCatalogClient",
    "ToolInfo",
]

# EmbeddedRouterBackend is NOT re-exported at package level because importing
# it requires AuraRouter to be installed.  Consumers should import it directly:
#   from auracode.routing.embedded import EmbeddedRouterBackend
