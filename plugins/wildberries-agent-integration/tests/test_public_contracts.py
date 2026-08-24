from __future__ import annotations

import asyncio

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from starlette.testclient import TestClient

from wildberries_agent_mcp.calculations import (
    inventory_forecast,
    replenishment_math,
    unit_economics,
)
from wildberries_agent_mcp.client import GatewayError, SellerGatewayClient
from wildberries_agent_mcp.config import Settings
from wildberries_agent_mcp.server import (
    _SellerIdentityTokenVerifier,
    _compact,
    _safe_handoff_url,
    _secure_base_url,
    build_server,
)


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


def test_inventory_forecast_uses_regional_demand_when_warehouse_stock_is_missing() -> None:
    result = inventory_forecast(
        deficit_rows=[
            {
                "nm_id": 101,
                "amount": 30,
                "qty": 0,
                "deficit": 20,
                "deficit_districts": [
                    {"district_name": "Central", "amount": 20, "deficit": 10, "qty": 0},
                    {"district_name": "Volga", "amount": 10, "deficit": 10, "qty": 0},
                ],
            }
        ],
        stock_rows=[],
        horizon_days=30,
        safety_days=7,
    )

    item = result["items"][0]
    assert item["destinations"]
    assert {row["destination_type"] for row in item["destinations"]} == {"district"}
    assert {row["warehouse"] for row in item["destinations"]} == {"Central", "Volga"}
    assert sum(row["quantity"] for row in item["destinations"]) == item["recommended_qty"]
    assert "regional demand" in item["warnings"][0]


def test_public_tool_list_contains_analytics_and_calculators() -> None:
    server = build_server(Settings(connect_url="https://seller.example/connect"))
    tools = asyncio.run(server.list_tools())

    names = {tool.name for tool in tools}
    assert names == {
        "wb_connect_supplier",
        "wb_list_suppliers",
        "wb_analytics_summary",
        "wb_competitor_analysis",
        "wb_wildberries_proxy",
        "wb_refresh_analytics",
        "wb_competitive_price",
        "wb_sales_by_region",
        "wb_sales_weather_impact",
        "wb_seo_analytics",
        "wb_warehouse_stock",
        "wb_unit_economics",
        "wb_upload_cost_price",
        "wb_replenishment_math",
        "wb_inventory_forecast",
    }


def test_public_tool_annotations_keep_private_reads_read_only() -> None:
    server = build_server(Settings(connect_url="https://seller.example/connect"))
    tools = asyncio.run(server.list_tools())
    annotations = {tool.name: tool.annotations for tool in tools}
    names = set(annotations)

    assert annotations["wb_connect_supplier"].readOnlyHint is False
    assert annotations["wb_upload_cost_price"].readOnlyHint is False
    assert annotations["wb_refresh_analytics"].readOnlyHint is False
    for name in names - {
        "wb_connect_supplier",
        "wb_upload_cost_price",
        "wb_refresh_analytics",
    }:
        assert annotations[name].readOnlyHint is True
        assert annotations[name].openWorldHint is False
    assert annotations["wb_wildberries_proxy"].readOnlyHint is True
    assert annotations["wb_wildberries_proxy"].destructiveHint is False


def test_supplier_handoff_supports_new_seller_registration_without_mcp_bearer() -> None:
    server = build_server(
        Settings(
            environment="production",
            connect_url="https://seller.bears.ru/authentication/registration",
        )
    )
    _, result = asyncio.run(
        server.call_tool("wb_connect_supplier", {"supplier_id_wb": 31460})
    )

    assert result["ok"] is True
    assert result["url"] == (
        "https://seller.bears.ru/authentication/registration?"
        "source=wildberries-agent-integration&supplier_id_wb=31460"
    )
    assert result["flow"].startswith("Регистрация пользователя Seller")


def test_cost_price_upload_rejects_invalid_input_before_gateway(monkeypatch) -> None:
    calls = []

    async def unexpected_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid input must stop before the gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    server = build_server(Settings(connect_url="https://seller.example/connect"))
    _, result = asyncio.run(
        server.call_tool(
            "wb_upload_cost_price",
            {
                "supplier_id_wb": 31460,
                "nm_id": 123456789,
                "cost_price": -1.0,
            },
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "invalid_cost_price_input"
    assert calls == []


def test_cost_price_upload_requires_bearer_for_explicit_input(monkeypatch) -> None:
    calls = []

    async def unexpected_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("missing bearer must stop before the gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    server = build_server(
        Settings(environment="production", gateway_url="https://seller.example")
    )
    _, result = asyncio.run(
        server.call_tool(
            "wb_upload_cost_price",
            {
                "supplier_id_wb": 31460,
                "nm_id": 123456789,
                "cost_price": 320.0,
            },
        )
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "auth_required"
    assert calls == []


def test_cost_price_upload_forwards_scoped_payload_without_provider_result(monkeypatch) -> None:
    calls = []

    async def fake_request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        return {
            "nm_id": 123456789,
            "cost_price": 320.0,
            "access_token": "must-not-return",
            "nested": {"authorization": "must-not-return", "status": "saved"},
        }

    monkeypatch.setattr(SellerGatewayClient, "request", fake_request)
    server = build_server(
        Settings(
            environment="test",
            gateway_url="http://seller.example",
            static_access_token="synthetic-agent-token",
        )
    )
    _, result = asyncio.run(
        server.call_tool(
            "wb_upload_cost_price",
            {
                "supplier_id_wb": 31460,
                "nm_id": 123456789,
                "cost_price": 320.0,
            },
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "authorization": "Bearer synthetic-agent-token",
            "path": "/price_management/cost_price",
            "method": "PUT",
            "params": {"supplier_id_wb": 31460},
            "json": {"nm_id": 123456789, "cost_price": 320.0},
            "request_id": None,
        }
    ]
    assert result == {
        "ok": True,
        "operation": "set_cost_price",
        "status": "updated",
        "supplier_id_wb": 31460,
        "nm_id": 123456789,
        "cost_price": 320.0,
    }


def test_wildberries_proxy_forwards_only_a_fixed_seller_operation(monkeypatch) -> None:
    calls = []

    async def fake_request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        return {"data": [{"region_name": "Москва", "nm_id": 123456789}]}

    monkeypatch.setattr(SellerGatewayClient, "request", fake_request)
    server = build_server(
        Settings(
            environment="test",
            gateway_url="http://seller.example",
            static_access_token="synthetic-agent-token",
        )
    )
    _, result = asyncio.run(
        server.call_tool(
            "wb_wildberries_proxy",
            {
                "supplier_id_wb": 31460,
                "operation": "seller_tape",
                "payload": {"nm_id": 123456789, "limit": 100, "page": 0},
            },
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "authorization": "Bearer synthetic-agent-token",
            "path": "/statistics/tape/v2",
            "method": "GET",
            "params": {
                "supplier_id_wb": 31460,
                "nm_id": 123456789,
                "limit": 100,
                "page": 0,
            },
            "json": None,
            "request_id": None,
        }
    ]
    assert result["data"] == {"data": [{"region_name": "Москва", "nm_id": 123456789}]}


def test_analytics_refresh_is_a_separate_bounded_write_tool(monkeypatch) -> None:
    calls = []

    async def fake_request(self, **kwargs):  # noqa: ARG001
        calls.append(kwargs)
        return {"task_id": "task-123", "status": "queued"}

    monkeypatch.setattr(SellerGatewayClient, "request", fake_request)
    server = build_server(
        Settings(
            environment="test",
            gateway_url="http://seller.example",
            static_access_token="synthetic-agent-token",
        )
    )
    _, result = asyncio.run(
        server.call_tool(
            "wb_refresh_analytics",
            {"supplier_id_wb": 31460, "period": 7},
        )
    )

    assert result["ok"] is True
    assert calls == [
        {
            "authorization": "Bearer synthetic-agent-token",
            "path": "/statistics/update/31460",
            "method": "POST",
            "params": {"period": 7},
            "request_id": None,
        }
    ]


@pytest.mark.parametrize("period", [0, 367, True])
def test_analytics_refresh_rejects_invalid_period_before_gateway(
    monkeypatch, period: object
) -> None:
    async def unexpected_request(*args, **kwargs):
        raise AssertionError("validation must stop before the gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    server = build_server(
        Settings(
            environment="test",
            gateway_url="http://seller.example",
            static_access_token="synthetic-agent-token",
        )
    )
    with pytest.raises(ToolError):
        asyncio.run(
            server.call_tool(
                "wb_refresh_analytics",
                {"supplier_id_wb": 31460, "period": period},
            )
        )


def test_public_bearer_is_verified_by_seller_identity_bridge(monkeypatch) -> None:
    calls = []

    async def fake_verify(self, authorization):  # noqa: ARG001
        calls.append(authorization)

    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", fake_verify)
    settings = Settings(environment="production")
    verifier = _SellerIdentityTokenVerifier(SellerGatewayClient(settings))

    access = asyncio.run(verifier.verify_token("opaque-agent-token"))

    assert access is not None
    assert access.scopes == ["wildberries-agent-free"]
    assert calls == ["Bearer opaque-agent-token"]


def test_rejected_public_bearer_does_not_receive_mcp_access(monkeypatch) -> None:
    async def reject(self, authorization):  # noqa: ARG001
        raise GatewayError("identity_bridge_rejected", status=401)

    monkeypatch.setattr(SellerGatewayClient, "verify_agent_token", reject)
    settings = Settings(environment="production")
    verifier = _SellerIdentityTokenVerifier(SellerGatewayClient(settings))

    assert asyncio.run(verifier.verify_token("rejected-agent-token")) is None


def test_wildberries_proxy_rejects_unknown_or_credential_payload_before_gateway(monkeypatch) -> None:
    calls = []

    async def unexpected_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("proxy validation must stop before the gateway")

    monkeypatch.setattr(SellerGatewayClient, "request", unexpected_request)
    server = build_server(
        Settings(
            environment="test",
            gateway_url="http://seller.example",
            static_access_token="synthetic-agent-token",
        )
    )

    for operation, payload, code in (
        ("arbitrary", {}, "proxy_operation_not_allowed"),
        ("seller_tape", {"nm_id": 123456789, "access_token": "raw"}, "proxy_payload_not_allowed"),
    ):
        _, result = asyncio.run(
            server.call_tool(
                "wb_wildberries_proxy",
                {"supplier_id_wb": 31460, "operation": operation, "payload": payload},
            )
        )
        assert result["ok"] is False
        assert result["error"]["code"] == code

    assert calls == []


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


def test_handoff_urls_reject_credentials_and_non_https_production_urls() -> None:
    assert _safe_handoff_url("https://seller.example/integration?token=secret", require_https=True) is None
    assert _safe_handoff_url("https://seller.example/integration#access-token", require_https=True) is None
    assert _safe_handoff_url("http://seller.example/integration", require_https=True) is None
    assert _safe_handoff_url("http://127.0.0.1:8000/integration", require_https=False)
    assert _secure_base_url("https://agents.example.com") == "https://agents.example.com"
    assert _secure_base_url("https://agents.example.com?token=secret") is None


def test_openai_domain_challenge_returns_exact_plain_text_token() -> None:
    server = build_server(
        Settings(
            public_url="https://mcp.example.com",
            auth_issuer="https://auth.example.com",
            openai_apps_challenge="openai-verification-token",
        )
    )

    with TestClient(server.streamable_http_app()) as client:
        response = client.get("/.well-known/openai-apps-challenge")

    assert response.status_code == 200
    assert response.text == "openai-verification-token"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["cache-control"] == "no-store"


def test_openai_domain_challenge_fails_closed_when_not_configured() -> None:
    server = build_server(Settings(openai_apps_challenge="bad token"))

    with TestClient(server.streamable_http_app()) as client:
        response = client.get("/.well-known/openai-apps-challenge")

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"


def test_oauth_resource_metadata_uses_canonical_issuer_and_free_scope() -> None:
    server = build_server(
        Settings(
            public_url="https://mcp.example.com",
            auth_issuer="https://auth.example.com",
        )
    )

    with TestClient(server.streamable_http_app()) as client:
        root_metadata = client.get("/.well-known/oauth-protected-resource")
        mcp_metadata = client.get("/.well-known/oauth-protected-resource/mcp")

    assert root_metadata.status_code == 200
    assert mcp_metadata.status_code == 200
    for response in (root_metadata, mcp_metadata):
        assert response.json()["resource"] == "https://mcp.example.com/mcp"
        assert response.json()["authorization_servers"] == [
            "https://auth.example.com/"
        ]
        assert response.json()["scopes_supported"] == ["wildberries-agent-free"]
