import asyncio

import pytest
from mcp.types import CallToolResult
from starlette.testclient import TestClient

from wildberries_agent_mcp.client import GatewayError, SellerGatewayClient
from wildberries_agent_mcp.config import Settings
from wildberries_agent_mcp.server import build_server


@pytest.mark.parametrize("status", [401, 403, 502])
def test_only_expired_auth_requests_relinking(monkeypatch, status):
    async def request(*args, **kwargs):
        raise GatewayError("upstream_rejected", status=status)

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    server = build_server(
        Settings(
            environment="test",
            static_access_token="synthetic-test-access",
            public_url="https://wb.example",
            auth_issuer="https://auth.example",
        )
    )
    result = asyncio.run(server.call_tool("wb_list_suppliers", {}))
    if status == 401:
        assert isinstance(result, CallToolResult)
        assert result.isError is True
        assert result.model_dump(by_alias=True)["_meta"] == {
            "mcp/www_authenticate": [
                'Bearer resource_metadata="https://wb.example/.well-known/oauth-protected-resource/mcp", error="invalid_token"'
                ', error_description="The access token is invalid or expired; reconnect the app."'
            ]
        }
        assert "synthetic-test-access" not in result.model_dump_json()
    else:
        assert not isinstance(result, CallToolResult)
        assert result[1]["error"]["status"] == status


def test_missing_auth_returns_protocol_challenge():
    server = build_server(
        Settings(
            public_url="https://wb.example",
            auth_issuer="https://auth.example",
        )
    )
    result = asyncio.run(server.call_tool("wb_list_suppliers", {}))
    assert isinstance(result, CallToolResult)
    assert result.isError is True
    assert result.structuredContent["error"]["code"] == "auth_required"


def test_relink_challenge_survives_http_protocol(monkeypatch):
    async def verify(*args, **kwargs):
        return None

    async def request(*args, **kwargs):
        raise GatewayError("upstream_unauthorized", status=401)

    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", verify)
    monkeypatch.setattr(SellerGatewayClient, "request", request)
    server = build_server(
        Settings(
            public_url="https://wb.example",
            auth_issuer="https://auth.example",
        )
    )
    with TestClient(
        server.streamable_http_app(), base_url="http://127.0.0.1:8080"
    ) as client:
        response = client.post(
            "/mcp",
            headers={
                "Authorization": "Bearer synthetic-test-access",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "wb_list_suppliers", "arguments": {}},
            },
        )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["isError"] is True
    assert "mcp/www_authenticate" in result["_meta"]
    assert "synthetic-test-access" not in response.text
