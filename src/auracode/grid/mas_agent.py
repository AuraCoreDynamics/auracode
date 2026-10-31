"""Node-local Multi-Agent System (MAS) client for AuraGrid deployment."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MAS_ENDPOINT = "http://127.0.0.1:8740"
DEFAULT_MAS_HEARTBEAT_INTERVAL = 60.0  # seconds


class NodeMasAgentClient:
    """Registers AuraCode as an autonomous agent in the node-local Multi-Agent System."""

    def __init__(
        self,
        mas_endpoint: str | None = None,
        mcp_endpoint: str | None = None,
        shim_endpoint: str | None = None,
        ui_endpoint: str | None = None,
        heartbeat_interval: float = DEFAULT_MAS_HEARTBEAT_INTERVAL,
    ) -> None:
        endpoint = mas_endpoint or os.environ.get("AURACODE_MAS_ENDPOINT", DEFAULT_MAS_ENDPOINT)
        proxy_url = os.environ.get("AURAGRID_PROXY_URL", "http://node-local:7077")
        self.mas_endpoint = endpoint.rstrip("/")
        self.mcp_endpoint = mcp_endpoint or f"{proxy_url}/mcp"
        self.shim_endpoint = shim_endpoint or f"{proxy_url}/api/AuraCode"
        self.ui_endpoint = ui_endpoint or f"{proxy_url}/ui/auracode"
        self.heartbeat_interval = heartbeat_interval
        self._registered = False
        self._heartbeat_task: asyncio.Task[None] | None = None

    @property
    def is_registered(self) -> bool:
        """Return True if successfully registered with node-local MAS."""
        return self._registered

    def build_registration_payload(self) -> dict[str, Any]:
        """Construct the MAS registration payload advertising AuraCode capabilities."""
        return {
            "agent_id": "auracode",
            "name": "AuraCode Autonomous Developer",
            "role": "code-engine",
            "endpoints": {
                "mcp": self.mcp_endpoint,
                "shim": self.shim_endpoint,
                "ui": self.ui_endpoint,
            },
            "capabilities": [
                "autonomous-act",
                "ast-repomap",
                "merge-conflict-resolution",
                "conventional-commits",
                "bundle-packaging",
                "verification-gate",
                "code-generation",
                "code-review",
            ],
            "status": "online",
        }

    async def register(self) -> bool:
        """Register AuraCode with the node-local MAS coordinator."""
        payload = self.build_registration_payload()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.mas_endpoint}/agents/register",
                    json=payload,
                )
            if resp.is_success:
                self._registered = True
                logger.info("Registered with node-local MAS coordinator at %s", self.mas_endpoint)
                return True
            logger.debug("MAS registration failed with status %d: %s", resp.status_code, resp.text)
            return False
        except Exception as exc:
            logger.debug(
                "Could not reach node-local MAS coordinator at %s: %s",
                self.mas_endpoint,
                exc,
            )
            return False

    async def deregister(self) -> bool:
        """Deregister AuraCode from the node-local MAS coordinator."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.mas_endpoint}/agents/deregister",
                    json={"agent_id": "auracode"},
                )
            self._registered = False
            return resp.is_success
        except Exception as exc:
            logger.debug("MAS deregistration error: %s", exc)
            self._registered = False
            return False

    async def heartbeat(self) -> bool:
        """Send a single heartbeat pulse to the node-local MAS coordinator."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    f"{self.mas_endpoint}/agents/heartbeat",
                    json={"agent_id": "auracode", "status": "online"},
                )
            return resp.is_success
        except Exception as exc:
            logger.debug("MAS heartbeat failed: %s", exc)
            return False

    async def _heartbeat_loop(self) -> None:
        """Background loop executing periodic heartbeats."""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                success = await self.heartbeat()
                if not success and self._registered:
                    # Attempt re-registration if heartbeat failed
                    await self.register()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Unexpected error in MAS heartbeat loop: %s", exc)

    def start_heartbeat(self) -> None:
        """Start the background heartbeat task."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop heartbeats and deregister cleanly."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        await self.deregister()
