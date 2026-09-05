from __future__ import annotations

import asyncio

from wildberries_agent_mcp.client import SellerGatewayClient
from wildberries_agent_mcp.config import Settings
from wildberries_agent_mcp.sandbox import (
    SANDBOX_ACCESS_TOKEN,
    SANDBOX_SUPPLIER_ID,
)
from wildberries_agent_mcp.server import _SellerIdentityTokenVerifier, build_server


def _sandbox_server():
    return build_server(
        Settings(
            environment="production",
            static_access_token=SANDBOX_ACCESS_TOKEN,
            gateway_url="https://seller.example",
            identity_bridge_url="https://identity.example",
        )
    )


def test_weather_reads_seller_sales_when_rows_omitted(monkeypatch) -> None:
    calls = []

    async def request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        return [{"nm_id": 123, "date": "2026-08-01", "region_name": "Пермь", "sales_records": 3}]

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    monkeypatch.setattr("wildberries_agent_mcp.server._auth_header", lambda *args: "Bearer test")
    _, result = asyncio.run(_sandbox_server().call_tool("wb_sales_weather_impact", {
        "supplier_id_wb": 1, "nm_id": 123,
        "date_from": "2026-08-01", "date_to": "2026-08-02",
        "weather_rows": [{"date": "2026-08-01", "region": "Пермь", "temperature_c": 20}],
    }))
    assert result["source"] == "seller_regional_daily_records"
    assert result["matched_observations"] == 1
    assert result["coverage"] == "stored_records_in_period"
    assert result["metric"] == "sales_records"
    assert calls[0]["path"] == "/statistics/sales/by-region/daily"
    assert calls[0]["params"]["date_from"] == "2026-08-01"
    assert calls[0]["params"]["supplier_id_wb"] == 1


def test_weather_sandbox_does_not_fetch_sales(monkeypatch) -> None:
    async def unexpected_request(self, **kwargs):  # noqa: ARG001
        raise AssertionError("sandbox must not fetch sales")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    _, result = asyncio.run(_sandbox_server().call_tool("wb_sales_weather_impact", {
        "supplier_id_wb": SANDBOX_SUPPLIER_ID, "nm_id": 123,
        "date_from": "2026-08-01", "date_to": "2026-08-02", "weather_rows": [],
    }))
    assert result["ok"] is False


def test_weather_rejects_incompatible_daily_response(monkeypatch) -> None:
    async def request(self, **kwargs):  # noqa: ARG001
        return {"unexpected": []}

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    monkeypatch.setattr("wildberries_agent_mcp.server._auth_header", lambda *args: "Bearer test")
    _, result = asyncio.run(_sandbox_server().call_tool("wb_sales_weather_impact", {
        "supplier_id_wb": 1, "nm_id": 123,
        "date_from": "2026-08-01", "date_to": "2026-08-02", "weather_rows": [],
    }))
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_regional_daily_response"


def test_sandbox_token_is_accepted_without_identity_bridge(monkeypatch) -> None:
    calls = []

    async def unexpected_verify(self, authorization):  # noqa: ARG001
        calls.append(authorization)
        raise AssertionError("sandbox token must not use the identity bridge")

    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", unexpected_verify)
    access = asyncio.run(
        _SellerIdentityTokenVerifier(SellerGatewayClient(Settings(environment="production"))).verify_token(
            SANDBOX_ACCESS_TOKEN
        )
    )

    assert access is not None
    assert access.client_id == "reviewer-sandbox"
    assert access.scopes == ["wildberries-agent-free"]
    assert calls == []


def test_sandbox_tools_are_fully_virtual_and_marked(monkeypatch) -> None:
    calls = []

    class UnexpectedHttpClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            raise AssertionError("sandbox path must not construct an HTTP client")

    async def unexpected_request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        raise AssertionError("sandbox path must not call Seller Gateway")

    async def unexpected_verify(self, authorization):  # noqa: ARG001
        calls.append(authorization)
        raise AssertionError("sandbox path must not call identity bridge")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", unexpected_verify)
    monkeypatch.setattr("wildberries_agent_mcp.client.httpx.AsyncClient", UnexpectedHttpClient)
    server = _sandbox_server()

    requests = [
        ("wb_list_suppliers", {}),
        (
            "wb_analytics_summary",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "date_from": "2026-01-01",
                "date_to": "2026-01-07",
                "include_finance": True,
                "include_price_table": True,
            },
        ),
        (
            "wb_wildberries_proxy",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "operation": "seller_tape",
                "payload": {"nm_id": 900000101, "limit": 10, "page": 0},
            },
        ),
        (
            "wb_warehouse_stock",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID, "nm_ids": [900000101]},
        ),
        (
            "wb_refresh_analytics",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID, "period": 7},
        ),
        (
            "wb_upload_cost_price",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID, "nm_id": 900000101, "cost_price": 320.0},
        ),
        (
            "wb_inventory_forecast",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID},
        ),
    ]

    for name, arguments in requests:
        _, result = asyncio.run(server.call_tool(name, arguments))
        assert result["ok"] is True
        assert result["sandbox"] is True
        assert result["synthetic"] is True
        assert result["identity"] == "reviewer-sandbox"
        assert result["supplier_id_wb"] == SANDBOX_SUPPLIER_ID
        if name == "wb_inventory_forecast":
            destination = result["data"]["items"][0]["destinations"][0]
            assert destination["warehouse"] != "[truncated]"
            assert isinstance(destination["quantity"], int)
            assert destination["quantity"] > 0

    assert calls == []


def test_sandbox_writes_are_simulated_and_invalid_inputs_are_marked(monkeypatch) -> None:
    async def unexpected_request(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("sandbox path must not call Seller Gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    server = _sandbox_server()

    _, upload = asyncio.run(
        server.call_tool(
            "wb_upload_cost_price",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID, "nm_id": 900000101, "cost_price": 320.0},
        )
    )
    assert upload["status"] == "simulated"
    assert upload["mutation"] == "none"

    _, wrong_supplier = asyncio.run(
        server.call_tool(
            "wb_refresh_analytics", {"supplier_id_wb": 31460, "period": 1}
        )
    )
    assert wrong_supplier["ok"] is False
    assert wrong_supplier["sandbox"] is True
    assert wrong_supplier["synthetic"] is True
    assert wrong_supplier["supplier_id_wb"] == SANDBOX_SUPPLIER_ID

    _, blocked_operation = asyncio.run(
        server.call_tool(
            "wb_wildberries_proxy",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "operation": "promotion_details",
                "payload": {},
            },
        )
    )
    assert blocked_operation["ok"] is False
    assert blocked_operation["sandbox"] is True
    assert blocked_operation["synthetic"] is True
