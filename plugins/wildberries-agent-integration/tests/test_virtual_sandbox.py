from __future__ import annotations

import asyncio

from starlette.testclient import TestClient

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
        )
    )


def test_weather_reads_seller_sales_when_rows_omitted(monkeypatch) -> None:
    calls = []

    async def verify(*_args, **_kwargs):
        return None

    async def request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        return [
            {
                "nm_id": 123,
                "date": "2026-08-01",
                "region_name": "Пермь",
                "sales_records": 3,
            }
        ]

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    monkeypatch.setattr(
        "wildberries_agent_mcp.server._auth_header", lambda *args: "Bearer test"
    )
    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", verify)
    _, result = asyncio.run(
        _sandbox_server().call_tool(
            "wb_sales_weather_impact",
            {
                "supplier_id_wb": 1,
                "nm_id": 123,
                "date_from": "2026-08-01",
                "date_to": "2026-08-02",
                "region": "Пермь",
                "weather_rows": [
                    {"date": "2026-08-01", "region": "Пермь", "temperature_c": 20}
                ],
            },
        )
    )
    assert result["source"] == "seller_regional_daily_records"
    assert result["matched_observations"] == 1
    assert result["coverage"] == "stored_records_in_period"
    assert result["metric"] == "sales_records"
    assert calls[0]["path"] == "/agent/statistics/sales/by-region/daily"
    assert calls[0]["params"]["date_from"] == "2026-08-01"
    assert calls[0]["params"]["region"] == "Пермь"
    assert calls[0]["params"]["supplier_id_wb"] == 1


def test_regional_report_labels_sales_records_without_net_sales_claim(
    monkeypatch,
) -> None:
    async def verify(*_args, **_kwargs):
        return None

    async def request(self, **kwargs):  # noqa: ARG001
        assert kwargs["path"] == "/agent/statistics/sales/by-region/daily"
        assert kwargs["params"]["date_to"] == "2026-08-02"
        return [
            {
                "nm_id": 123,
                "date": "2026-08-01",
                "region_name": "Пермь",
                "sales_records": 3,
                "sales_records_value": 90,
            }
        ]

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    monkeypatch.setattr(
        "wildberries_agent_mcp.server._auth_header", lambda *args: "Bearer test"
    )
    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", verify)
    _, result = asyncio.run(
        _sandbox_server().call_tool(
            "wb_sales_by_region",
            {
                "supplier_id_wb": 1,
                "nm_id": 123,
                "date_from": "2026-08-01",
                "date_to": "2026-08-02",
            },
        )
    )
    assert result["data"]["totals"]["sales_records"] == 3
    assert result["data"]["totals"]["sales_records_value"] == 90
    assert "sales" not in result["data"]["totals"]
    assert "revenue" not in result["data"]["regions"][0]


def test_weather_sandbox_uses_matching_virtual_rows_without_fetching(
    monkeypatch,
) -> None:
    async def unexpected_request(self, **kwargs):  # noqa: ARG001
        raise AssertionError("sandbox must not fetch sales")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    _, result = asyncio.run(
        _sandbox_server().call_tool(
            "wb_sales_weather_impact",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "nm_id": 123,
                "date_from": "2026-08-01",
                "date_to": "2026-08-02",
                "weather_rows": [],
            },
        )
    )
    assert result["ok"] is True
    assert result["sandbox"] is True
    assert result["synthetic"] is True
    assert result["source"] == "virtual_fixture"
    assert result["matched_observations"] == 2


def test_weather_rejects_incompatible_daily_response(monkeypatch) -> None:
    async def request(self, **kwargs):  # noqa: ARG001
        return {"unexpected": []}

    monkeypatch.setattr(SellerGatewayClient, "request", request)
    monkeypatch.setattr(
        "wildberries_agent_mcp.server._auth_header", lambda *args: "Bearer test"
    )
    _, result = asyncio.run(
        _sandbox_server().call_tool(
            "wb_sales_weather_impact",
            {
                "supplier_id_wb": 1,
                "nm_id": 123,
                "date_from": "2026-08-01",
                "date_to": "2026-08-02",
                "weather_rows": [],
            },
        )
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_regional_daily_response"


def test_sandbox_token_is_accepted_without_gateway(monkeypatch) -> None:
    calls = []

    async def unexpected_verify(self, authorization):  # noqa: ARG001
        calls.append(authorization)
        raise AssertionError("sandbox token must not use Seller Gateway")

    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", unexpected_verify)
    access = asyncio.run(
        _SellerIdentityTokenVerifier(
            SellerGatewayClient(Settings(environment="production"))
        ).verify_token(SANDBOX_ACCESS_TOKEN)
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
        raise AssertionError("sandbox path must not call Seller Gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", unexpected_verify)
    monkeypatch.setattr(
        "wildberries_agent_mcp.client.httpx.AsyncClient", UnexpectedHttpClient
    )
    requests = [
        ("wb_connect_supplier", {}),
        ("wb_connection_status", {}),
        ("wb_connect_telegram", {}),
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
            "wb_competitor_analysis",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "nm_id": 900000101,
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
            "wb_competitive_price",
            {
                "seller_price": 1290.0,
                "competitor_prices": [1190.0, 1250.0, 1390.0],
                "cost_price": 700.0,
                "target_margin_percent": 25.0,
            },
        ),
        (
            "wb_sales_by_region",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "date_from": "2026-01-01",
                "date_to": "2026-01-14",
            },
        ),
        (
            "wb_sales_weather_impact",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "nm_id": 900000101,
                "region": "Екатеринбург",
                "date_from": "2026-01-01",
                "date_to": "2026-01-14",
            },
        ),
        (
            "wb_seo_analytics",
            {
                "title": "Термокружка 500 мл",
                "description": "Стальная термокружка сохраняет тепло, герметичная крышка",
                "keywords": ["термокружка", "кружка дорожная", "термос"],
            },
        ),
        (
            "wb_warehouse_stock",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID, "nm_ids": [900000101]},
        ),
        (
            "wb_unit_economics",
            {
                "price": 1200.0,
                "cost_price": 320.0,
                "commission_percent": 18.0,
                "logistics_per_unit": 80.0,
                "tax_percent": 6.0,
            },
        ),
        (
            "wb_refresh_analytics",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID, "period": 7},
        ),
        (
            "wb_upload_cost_price",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "nm_id": 900000101,
                "cost_price": 320.0,
                "confirm": True,
            },
        ),
        (
            "wb_replenishment_math",
            {
                "daily_sales": 3.2,
                "current_stock": 20,
                "target_days": 30,
                "safety_days": 5,
                "inbound_qty": 10,
            },
        ),
        (
            "wb_inventory_forecast",
            {"supplier_id_wb": SANDBOX_SUPPLIER_ID},
        ),
    ]

    assert len(requests) == 17
    for _fresh_session in range(2):
        server = _sandbox_server()
        with TestClient(
            server.streamable_http_app(), base_url="http://127.0.0.1:8080"
        ) as client:
            for request_id, (name, arguments) in enumerate(requests, start=1):
                response = client.post(
                    "/mcp",
                    headers={
                        "Authorization": f"Bearer {SANDBOX_ACCESS_TOKEN}",
                        "Accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": arguments},
                    },
                )
                assert response.status_code == 200, name
                result = response.json()["result"]["structuredContent"]
                assert result["ok"] is True, name
                assert result["sandbox"] is True, name
                assert result["synthetic"] is True, name
                assert result["identity"] == "reviewer-sandbox", name
                assert result["supplier_id_wb"] == SANDBOX_SUPPLIER_ID, name
                if name == "wb_inventory_forecast":
                    destination = result["data"]["items"][0]["destinations"][0]
                    assert destination["warehouse"] != "[truncated]"
                    assert isinstance(destination["quantity"], int)
                    assert destination["quantity"] > 0

    assert calls == []


def test_sandbox_writes_are_simulated_and_invalid_inputs_are_marked(
    monkeypatch,
) -> None:
    async def unexpected_request(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("sandbox path must not call Seller Gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    server = _sandbox_server()

    _, preview = asyncio.run(
        server.call_tool(
            "wb_upload_cost_price",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "nm_id": 900000101,
                "cost_price": 320.0,
            },
        )
    )
    assert preview["ok"] is False
    assert preview["error"]["code"] == "confirmation_required"
    assert preview["requested"] == {
        "supplier_id_wb": SANDBOX_SUPPLIER_ID,
        "nm_id": 900000101,
        "cost_price": 320.0,
    }
    assert preview["sandbox"] is True
    assert preview["synthetic"] is True

    _, upload = asyncio.run(
        server.call_tool(
            "wb_upload_cost_price",
            {
                "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                "nm_id": 900000101,
                "cost_price": 320.0,
                "confirm": True,
            },
        )
    )
    assert upload["status"] == "simulated"
    assert upload["mutation"] == "none"

    _, wrong_supplier = asyncio.run(
        server.call_tool("wb_refresh_analytics", {"supplier_id_wb": 31460, "period": 1})
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
