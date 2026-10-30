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
    """Client hook connecting AuraCode to AuraCore Assist via MCP over HTTP."""

    def __init__(self, endpoint: str | None = None) -> None:
        self.endpoint = (endpoint or DEFAULT_ASSIST_ENDPOINT).rstrip("/")
        # Derive MCP base URL from endpoint (e.g. http://127.0.0.1:8290/api/assist -> 8290)
        if "/api/assist" in self.endpoint:
            self.base_url = self.endpoint.split("/api/assist")[0]
        else:
            self.base_url = self.endpoint

    @property
    def is_available(self) -> bool:
        """Checks if AuraCore Assist service is active and reachable via health probe."""
        probe_paths = [
            f"{self.base_url}/healthz",
            f"{self.endpoint}/health",
            f"{self.base_url}/api/assist/health",
        ]
        for path in probe_paths:
            try:
                r = httpx.get(path, timeout=1.5)
                if r.status_code == 200:
                    return True
            except Exception:
                continue
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
        """Queries AuraCore Assist service via standard MCP JSON-RPC 2.0 (POST /mcp/message)."""
        # 1. Primary path: FastMCP JSON-RPC 2.0 tool invocation over HTTP
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                rpc_req = {
                    "jsonrpc": "2.0",
                    "id": "auracode-query",
                    "method": "tools/call",
                    "params": {
                        "name": "auracore_assist_query",
                        "arguments": {"query": query, "model_family": model_family},
                    },
                }
                r = await client.post(f"{self.base_url}/mcp/message", json=rpc_req)
                if r.status_code == 200:
                    data = r.json()
                    res = data.get("result", {})
                    if "data" in res and isinstance(res["data"], dict):
                        return res["data"]
                    if "content" in res and res["content"]:
                        raw_text = res["content"][0].get("text", "")
                        try:
                            import json

                            return json.loads(raw_text)
                        except Exception:
                            return {"response_text": raw_text}
        except Exception as ex:
            log.debug("auracode.mcp_query_fallback", error=str(ex))

        # 2. Fallback path: REST /api/assist/ask
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
        """Executes administrative grid management actions via MCP JSON-RPC (POST /mcp/message)."""
        # 1. Primary path: FastMCP JSON-RPC 2.0 tool invocation
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                rpc_req = {
                    "jsonrpc": "2.0",
                    "id": "auracode-manage",
                    "method": "tools/call",
                    "params": {
                        "name": "auracore_assist_manage",
                        "arguments": {"command": action},
                    },
                }
                r = await client.post(f"{self.base_url}/mcp/message", json=rpc_req)
                if r.status_code == 200:
                    data = r.json()
                    res = data.get("result", {})
                    if "data" in res and isinstance(res["data"], dict):
                        return res["data"]
                    if "content" in res and res["content"]:
                        raw_text = res["content"][0].get("text", "")
                        try:
                            import json

                            return json.loads(raw_text)
                        except Exception:
                            return {"message": raw_text}
        except Exception as ex:
            log.debug("auracode.mcp_manage_fallback", error=str(ex))

        # 2. Fallback path: REST /api/assist/manage
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
