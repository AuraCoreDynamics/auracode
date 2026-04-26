"""Catalog registration with AuraRouter — push-based service discovery."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Default registration config — URL is None to require explicit opt-in.
DEFAULT_AURAROUTER_URL: str | None = None
DEFAULT_HEARTBEAT_INTERVAL = 300  # 5 minutes
MAX_BACKOFF = 60  # seconds
DEFAULT_MAX_RETRIES = 0  # 0 = unlimited


def build_catalog_artifact(mcp_endpoint: str) -> dict[str, Any]:
    """Build a CatalogArtifact payload matching AuraRouter's schema."""
    return {
        "artifact_id": "auracode-mcp",
        "kind": "service",
        "display_name": "AuraCode",
        "capabilities": [
            "code-generation",
            "code-review",
            "code-refactoring",
            "code-explanation",
            "security-review",
        ],
        "supported_intents": [
            "GENERATE_CODE",
            "EDIT_CODE",
            "REVIEW",
            "EXPLAIN_CODE",
        ],
        "spec": {
            "mcp_endpoint": mcp_endpoint,
            "description": "AuraCode multi-adapter AI coding assistant",
        },
    }


class CatalogRegistrar:
    """Handles registration lifecycle with AuraRouter catalog."""

    def __init__(
        self,
        mcp_endpoint: str,
        aurarouter_url: str | None = DEFAULT_AURAROUTER_URL,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
    ):
        self._mcp_endpoint = mcp_endpoint
        self._aurarouter_url = aurarouter_url.rstrip("/") if aurarouter_url else None
        self._heartbeat_interval = heartbeat_interval
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._registered = False

    async def register(self) -> bool:
        """Attempt to register with AuraRouter. Returns True on success."""
        if self._aurarouter_url is None:
            logger.debug("AuraRouter URL not configured; skipping registration.")
            return False
        payload = build_catalog_artifact(self._mcp_endpoint)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._aurarouter_url}/catalog/register",
                    json=payload,
                )
            if resp.is_success:
                self._registered = True
                logger.info(
                    "Registered with AuraRouter catalog at %s", self._aurarouter_url
                )
                return True
            logger.warning(
                "Catalog registration failed: %d %s", resp.status_code, resp.text
            )
            return False
        except Exception as exc:
            logger.warning("Catalog registration error: %s", exc)
            return False

    async def deregister(self) -> None:
        """Deregister from AuraRouter catalog."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self._aurarouter_url}/catalog/remove",
                    json={"artifact_id": "auracode-mcp"},
                )
            self._registered = False
            logger.info("Deregistered from AuraRouter catalog")
        except httpx.HTTPError as exc:
            logger.debug("Catalog deregistration error (ignored): %s", exc)

    async def _heartbeat_loop(self) -> None:
        """Periodically re-register to keep the catalog entry alive."""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self.register()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Heartbeat error (will retry next cycle): %s", exc)

    async def start_heartbeat(self) -> None:
        """Start periodic re-registration heartbeat."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self) -> None:
        """Stop heartbeat and deregister."""
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        await self.deregister()

    async def start_with_retry(
        self, max_retries: int = DEFAULT_MAX_RETRIES
    ) -> None:
        """Start registration with exponential backoff retry, then begin heartbeat.

        Args:
            max_retries: Maximum retry attempts. 0 = unlimited.
        """
        if self._aurarouter_url is None:
            logger.info("AuraRouter URL not configured; catalog registration disabled.")
            return
        delay = 1.0
        attempt = 0
        while max_retries == 0 or attempt < max_retries:
            try:
                if await self.register():
                    await self.start_heartbeat()
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Registration attempt %d error: %s", attempt + 1, exc)
            attempt += 1
            logger.info("Catalog registration retry in %.0fs (attempt %d)", delay, attempt)
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_BACKOFF)
        logger.error(
            "Catalog registration failed after %d attempts; giving up.", max_retries
        )
