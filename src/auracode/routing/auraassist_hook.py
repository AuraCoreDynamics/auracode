"""Client hook delegating architectural queries to AuraCore Assist on AuraGrid."""

from __future__ import annotations

import os
from typing import Any

import httpx
import structlog

from auracode.models.request import EngineRequest

log = structlog.get_logger()

DEFAULT_ASSIST_ENDPOINT = os.environ.get(
    "AURACORE_ASSIST_ENDPOINT", "http://127.0.0.1:8290/api/assist"
)


class AuraAssistRoutingClient:
    """Client hook connecting AuraCode terminal/IDE engine to AuraCore Assist on AuraGrid."""

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or DEFAULT_ASSIST_ENDPOINT).rstrip("/")

    @property
    def is_available(self) -> bool:
        """Checks if AuraCore Assist service is active and reachable."""
        try:
            r = httpx.get(f"{self.endpoint}/health", timeout=1.5)
            return r.status_code == 200
        except Exception:
            return False

    def should_route_to_assist(self, request: EngineRequest) -> bool:
        """Determines if the request involves AuraCore architectural guidance or grid management."""
        # 1. Explicit routing hints in options
        hints = request.options.get("routing_hints", []) if request.options else []
        if hints and any("auracore" in str(h).lower() for h in hints):
            return True

        # 2. Text heuristics in prompt
        prompt_lower = (request.prompt or "").lower()
        keywords = (
            "auragrid",
            "auraxlm",
            "aurarouter",
            "auracode",
            "fencing token",
            "cas lease",
            "speculative decoding",
            "swim gossip",
        )
        return any(k in prompt_lower for k in keywords)

    async def query_assist(
        self,
        query: str,
        model_family: str = "phi",
    ) -> dict[str, Any] | None:
        """Queries the AuraCore Assist service for specialized technical answers."""
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                r = await client.post(
                    f"{self.endpoint}/ask",
                    json={"query": query, "model_family": model_family},
                )
                if r.status_code == 200:
                    return r.json()
        except Exception as ex:
            log.warning("auracode.auraassist_query_failed", error=str(ex))
        return None

    async def execute_grid_command(
        self,
        action: str,
        parameters: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Executes administrative grid management actions via AuraCore Assist."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{self.endpoint}/manage",
                    json={"action": action, "parameters": parameters or {}},
                )
                if r.status_code == 200:
                    return r.json()
        except Exception as ex:
            log.warning("auracode.auraassist_manage_failed", error=str(ex))
        return None
