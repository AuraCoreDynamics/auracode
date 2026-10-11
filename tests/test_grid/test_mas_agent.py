"""Unit tests for NodeMasAgentClient in grid/mas_agent.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from auracode.grid.mas_agent import NodeMasAgentClient


@pytest.mark.asyncio
async def test_mas_agent_client_payload() -> None:
    client = NodeMasAgentClient(
        mas_endpoint="http://127.0.0.1:8740",
        mcp_endpoint="http://127.0.0.1:8741",
    )
    payload = client.build_registration_payload()
    assert payload["agent_id"] == "auracode"
    assert "autonomous-act" in payload["capabilities"]
    assert "ast-repomap" in payload["capabilities"]
    assert "bundle-packaging" in payload["capabilities"]
    assert payload["endpoints"]["mcp"] == "http://127.0.0.1:8741"
    assert payload["status"] == "online"


@pytest.mark.asyncio
async def test_mas_agent_client_register_success() -> None:
    client = NodeMasAgentClient(mas_endpoint="http://127.0.0.1:8740")
    mock_resp = httpx.Response(200, json={"status": "registered"})

    with patch("auracode.grid.mas_agent.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        success = await client.register()
        assert success is True
        assert client.is_registered is True
        mock_http.post.assert_called_once()
        call_url = mock_http.post.call_args[0][0]
        assert "http://127.0.0.1:8740/agents/register" in call_url


@pytest.mark.asyncio
async def test_mas_agent_client_graceful_on_connection_error() -> None:
    client = NodeMasAgentClient(mas_endpoint="http://127.0.0.1:8740")

    with patch("auracode.grid.mas_agent.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.ConnectError("Connection refused")
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        success = await client.register()
        assert success is False
        assert client.is_registered is False


@pytest.mark.asyncio
async def test_mas_agent_client_heartbeat() -> None:
    client = NodeMasAgentClient(mas_endpoint="http://127.0.0.1:8740")
    mock_resp = httpx.Response(200, json={"ok": True})

    with patch("auracode.grid.mas_agent.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        success = await client.heartbeat()
        assert success is True
        mock_http.post.assert_called_once()
        assert "http://127.0.0.1:8740/agents/heartbeat" in mock_http.post.call_args[0][0]
