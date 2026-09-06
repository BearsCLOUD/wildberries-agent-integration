from __future__ import annotations

import asyncio

import httpx
from mcp.types import CallToolResult

from wildberries_agent_mcp.client import SellerGatewayClient
from wildberries_agent_mcp.config import Settings
from wildberries_agent_mcp.server import _SellerIdentityTokenVerifier, build_server


def test_calculators_are_noauth_but_supplier_reads_return_auth_required() -> None:
    server = build_server(Settings())
    _, calculator = asyncio.run(
        server.call_tool(
            "wb_replenishment_math",
            {"daily_sales": 2, "current_stock": 1, "target_days": 7, "safety_days": 1},
        )
    )
    private_result = asyncio.run(server.call_tool("wb_list_suppliers", {}))
    assert isinstance(private_result, CallToolResult)
    private = private_result.structuredContent
    assert calculator["ok"] is True
    assert private is not None
    assert private["error"]["code"] == "auth_required"


def test_new_connection_tools_forward_bearer_to_agent_paths(monkeypatch) -> None:
    calls: list[dict] = []

    async def request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        return {
            "url": "https://seller.example/connect",
            "status": "pending",
            "access_token": "omit",
        }

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    server = build_server(
        Settings(
            environment="development",
            static_access_token="oauth",
            gateway_url="https://gateway.example",
        )
    )
    _, supplier = asyncio.run(
        server.call_tool("wb_connect_supplier", {"supplier_id_wb": 42})
    )
    _, status = asyncio.run(server.call_tool("wb_connection_status", {}))
    _, telegram = asyncio.run(server.call_tool("wb_connect_telegram", {}))

    assert calls[0]["path"] == "/agent/connection/supplier"
    assert calls[0]["method"] == "POST"
    assert calls[0]["json"] == {"supplier_id_wb": 42}
    assert calls[1]["path"] == "/agent/connection/status"
    assert calls[2]["path"] == "/agent/connection/telegram"
    assert all(call["authorization"] == "Bearer oauth" for call in calls)
    assert supplier == {
        "ok": True,
        "url": "https://seller.example/connect",
        "status": "pending",
    }
    assert status["status"] == "pending"
    assert telegram["status"] == "pending"
    assert "access_token" not in supplier


def test_identity_verification_uses_get_agent_identity_without_exchange(
    monkeypatch,
) -> None:
    calls: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, **kwargs):
            calls.append(kwargs)
            return httpx.Response(200, json={"linked": False})

    monkeypatch.setattr(
        "wildberries_agent_mcp.client.httpx.AsyncClient", FakeAsyncClient
    )
    client = SellerGatewayClient(
        Settings(environment="production", gateway_url="https://gateway.example")
    )
    access = asyncio.run(
        _SellerIdentityTokenVerifier(client).verify_token("opaque-agent-token")
    )
    assert access is not None
    assert access.client_id == "agent-subject"
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "https://gateway.example/agent/identity"
    assert calls[0]["headers"] == {"Authorization": "Bearer opaque-agent-token"}
