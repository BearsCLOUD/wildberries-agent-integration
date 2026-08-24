from __future__ import annotations

import asyncio

import pytest

from wildberries_agent_mcp.calculations import (
    inventory_forecast,
    replenishment_math,
    unit_economics,
)
from wildberries_agent_mcp.client import GatewayError, SellerGatewayClient
from wildberries_agent_mcp.config import Settings
from wildberries_agent_mcp.server import _compact, build_server


def test_unit_economics_returns_profit_margin_and_target_price() -> None:
    result = unit_economics(
        price=1_000,
        cost_price=300,
        commission_percent=20,
        logistics_per_unit=50,
        storage_per_unit=10,
        advertising_per_unit=20,
        tax_percent=6,
        discount_percent=10,
        target_margin_percent=20,
    )

    assert result["net_price"] == 900.0
    assert result["profit"] == 286.0
    assert result["margin_percent"] == 31.78
    assert result["break_even_price"] == 570.57
    assert result["target_margin_price"] == 781.89


def test_unit_economics_rejects_non_positive_price() -> None:
    with pytest.raises(ValueError, match="price must be greater than zero"):
        unit_economics(price=0, cost_price=10, commission_percent=10)


def test_replenishment_math_accounts_for_inbound_units() -> None:
    result = replenishment_math(
        daily_sales=3.2,
        current_stock=20,
        target_days=30,
        safety_days=5,
        inbound_qty=10,
    )

    assert result["target_stock"] == 112
    assert result["recommended_qty"] == 82


def test_inventory_forecast_allocates_replenishment_to_warehouses() -> None:
    result = inventory_forecast(
        deficit_rows=[{"nm_id": 101, "qty": 2, "deficit": 5, "amount": 300}],
        stock_rows=[
            {"nmId": 101, "warehouseName": "Moscow", "quantity": 100},
            {"nmId": 101, "warehouseName": "Kazan", "quantity": 10},
        ],
        horizon_days=30,
        safety_days=7,
    )

    item = result["items"][0]
    assert item["recommended_qty"] == 368
    assert sum(row["quantity"] for row in item["destinations"]) == 368
    assert item["destinations"][0]["warehouse"] == "Moscow"
    assert item["destinations"][1]["warehouse"] == "Kazan"
    assert item["destinations"][1]["quantity"] > item["destinations"][0]["quantity"]


def test_public_tool_list_contains_analytics_and_calculators() -> None:
    server = build_server(Settings(connect_url="https://seller.example/connect"))
    tools = asyncio.run(server.list_tools())

    names = {tool.name for tool in tools}
    assert names == {
        "wb_connect_supplier",
        "wb_list_suppliers",
        "wb_analytics_summary",
        "wb_warehouse_stock",
        "wb_unit_economics",
        "wb_replenishment_math",
        "wb_inventory_forecast",
    }


def test_credential_fields_are_removed_from_nested_results() -> None:
    result = _compact(
        {
            "supplier_id": 31460,
            "access_token": "do-not-return",
            "nested": {
                "Authorization": "Bearer do-not-return",
                "cookie": "session=do-not-return",
                "visible": "ok",
            },
        }
    )

    assert result == {
        "supplier_id": 31460,
        "nested": {"visible": "ok"},
    }


def test_production_requires_identity_bridge_before_gateway_call() -> None:
    client = SellerGatewayClient(
        Settings(environment="production", gateway_url="https://seller.example")
    )

    with pytest.raises(GatewayError, match="identity_bridge_not_configured"):
        asyncio.run(
            client.request(
                authorization="Bearer synthetic-mcp-token",
                path="/suppliers",
            )
        )
