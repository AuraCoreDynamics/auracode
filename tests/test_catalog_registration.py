"""Tests for catalog registration with AuraRouter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from auracode.catalog_registration import (
    CatalogRegistrar,
    build_catalog_artifact,
)


class TestBuildCatalogArtifact:
    def test_returns_correct_schema(self):
        artifact = build_catalog_artifact("http://localhost:8741")

        assert artifact["artifact_id"] == "auracode-mcp"
        assert artifact["kind"] == "service"
        assert artifact["display_name"] == "AuraCode"
        assert "code-generation" in artifact["capabilities"]
        assert "security-review" in artifact["capabilities"]
        assert "GENERATE_CODE" in artifact["supported_intents"]
        assert "REVIEW" in artifact["supported_intents"]
        assert artifact["spec"]["mcp_endpoint"] == "http://localhost:8741"

    def test_uses_provided_endpoint(self):
        artifact = build_catalog_artifact("http://10.0.0.5:9999")
        assert artifact["spec"]["mcp_endpoint"] == "http://10.0.0.5:9999"


class TestCatalogRegistrar:
    @pytest.fixture
    def registrar(self):
        return CatalogRegistrar(
            mcp_endpoint="http://localhost:8741",
            aurarouter_url="http://localhost:8321",
            heartbeat_interval=1.0,
        )

    @pytest.mark.asyncio
    async def test_register_success(self, registrar):
        mock_response = httpx.Response(200, json={"ok": True})
        with patch("auracode.catalog_registration.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await registrar.register()

        assert result is True
        assert registrar._registered is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/catalog/register" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_register_failure_status(self, registrar):
        mock_response = httpx.Response(500, text="Internal Server Error")
        with patch("auracode.catalog_registration.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await registrar.register()

        assert result is False
        assert registrar._registered is False

    @pytest.mark.asyncio
    async def test_register_connection_error(self, registrar):
        with patch("auracode.catalog_registration.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await registrar.register()

        assert result is False

    @pytest.mark.asyncio
    async def test_start_with_retry_retries_on_failure(self, registrar):
        call_count = 0

        async def mock_register():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return False
            registrar._registered = True
            return True

        registrar.register = mock_register
        registrar.start_heartbeat = AsyncMock()

        # Patch sleep to avoid real delays
        with patch("auracode.catalog_registration.asyncio.sleep", new_callable=AsyncMock):
            await registrar.start_with_retry()

        assert call_count == 3
        registrar.start_heartbeat.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_heartbeat_and_deregisters(self, registrar):
        registrar.deregister = AsyncMock()
        # Start a fake heartbeat task
        registrar._heartbeat_task = asyncio.create_task(asyncio.sleep(3600))

        await registrar.stop()

        assert registrar._heartbeat_task is None
        registrar.deregister.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_continues_when_aurarouter_unreachable(self):
        """Registration failure should never block the caller."""
        registrar = CatalogRegistrar(
            mcp_endpoint="http://localhost:8741",
            aurarouter_url="http://192.0.2.1:9999",  # unreachable
            heartbeat_interval=1.0,
        )

        # Mock register to fail, then succeed on 2nd call
        call_count = 0
        original_register = registrar.register

        async def mock_register():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return False
            return True

        registrar.register = mock_register
        registrar.start_heartbeat = AsyncMock()

        with patch("auracode.catalog_registration.asyncio.sleep", new_callable=AsyncMock):
            # Run as background task — should not block
            task = asyncio.create_task(registrar.start_with_retry())
            await task

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_deregister_ignores_errors(self, registrar):
        with patch("auracode.catalog_registration.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            # Should not raise
            await registrar.deregister()

    @pytest.mark.asyncio
    async def test_heartbeat_calls_register_periodically(self, registrar):
        register_calls = 0

        async def mock_register():
            nonlocal register_calls
            register_calls += 1
            return True

        registrar.register = mock_register

        sleep_count = 0
        original_sleep = asyncio.sleep

        async def counting_sleep(duration):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                raise asyncio.CancelledError
            # Don't actually sleep

        with patch("auracode.catalog_registration.asyncio.sleep", side_effect=counting_sleep):
            await registrar.start_heartbeat()
            try:
                await registrar._heartbeat_task
            except asyncio.CancelledError:
                pass

        assert register_calls >= 1
