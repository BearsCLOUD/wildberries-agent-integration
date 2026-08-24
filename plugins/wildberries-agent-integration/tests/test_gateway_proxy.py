from __future__ import annotations

import pytest

from wildberries_agent_mcp.gateway_proxy import (
    allowed_operations,
    build_gateway_request,
)


def test_gateway_operations_are_fixed_and_supplier_scoped() -> None:
    assert allowed_operations() == (
        "competitor_cards",
        "competitor_orders",
        "card_details",
        "card_photos",
        "price_block",
        "feedbacks",
        "feedback_average",
        "wb_api_capabilities",
        "wb_api_operation",
        "seller_tape",
        "analytics_refresh",
        "analytics_refresh_status",
        "kt_statistics_period",
        "kt_statistics_grouped",
        "promotion_list",
        "promotion_details",
    )


def test_gateway_request_contains_no_caller_controlled_url_method_or_token() -> None:
    request = build_gateway_request(
        operation="seller_tape",
        supplier_id_wb=31460,
        payload={"nm_id": 123456789},
    )

    assert request == {
        "path": "/statistics/tape/v2",
        "method": "GET",
        "params": {
            "supplier_id_wb": 31460,
            "nm_id": 123456789,
            "limit": 100,
            "page": 0,
        },
        "json": None,
        "requires_supplier": True,
    }


@pytest.mark.parametrize(
    ("operation", "payload", "error"),
    [
        ("unknown", {}, "proxy_operation_not_allowed"),
        ("seller_tape", {"nm_id": 123456789, "access_token": "raw"}, "proxy_payload_not_allowed"),
        ("seller_tape", {"nm_id": 123456789, "path": "https://evil.example"}, "proxy_payload_not_allowed"),
        ("seller_tape", {"nm_id": 123456789, "limit": 1001}, "proxy_payload_invalid"),
    ],
)
def test_gateway_request_rejects_untrusted_controls(
    operation: str, payload: dict[str, object], error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        build_gateway_request(
            operation=operation,
            supplier_id_wb=31460,
            payload=payload,
        )


def test_supplier_scoped_body_is_fixed_to_the_selected_supplier() -> None:
    request = build_gateway_request(
        operation="kt_statistics_period",
        supplier_id_wb=31460,
        payload={"date_from": "2026-08-01", "date_to": "2026-08-24"},
    )

    assert request["path"] == "/integration-wb/kt/statistics/period"
    assert request["method"] == "POST"
    assert request["params"] == {"supplier_id_wb": 31460}
    assert request["json"] == {"date_from": "2026-08-01", "date_to": "2026-08-24"}
    assert request["requires_supplier"] is True


def test_analytics_refresh_and_status_use_existing_seller_queue_contract() -> None:
    refresh = build_gateway_request(
        operation="analytics_refresh",
        supplier_id_wb=31460,
        payload={"period": 7},
    )
    status = build_gateway_request(
        operation="analytics_refresh_status",
        supplier_id_wb=31460,
    )

    assert refresh == {
        "path": "/statistics/update/31460",
        "method": "POST",
        "params": {"period": 7},
        "json": None,
        "requires_supplier": True,
    }
    assert status == {
        "path": "/suppliers_analytics/status_update/31460",
        "method": "GET",
        "params": {"type_update": "statistics"},
        "json": None,
        "requires_supplier": True,
    }


@pytest.mark.parametrize("period", [0, 367, True, "7"])
def test_analytics_refresh_rejects_unbounded_period(period: object) -> None:
    with pytest.raises(ValueError, match="proxy_payload_invalid"):
        build_gateway_request(
            operation="analytics_refresh",
            supplier_id_wb=31460,
            payload={"period": period},
        )


def test_feedback_operations_use_owned_supplier_and_bounded_inputs() -> None:
    feedbacks = build_gateway_request(
        operation="feedbacks",
        supplier_id_wb=31460,
        payload={"nm_id": 123456789, "is_answered": False, "take": 50},
    )
    average = build_gateway_request(
        operation="feedback_average",
        supplier_id_wb=31460,
        payload={"nm_ids": [123456789, 987654321]},
    )

    assert feedbacks == {
        "path": "/feedbacks/get_feedbacks",
        "method": "GET",
        "params": {
            "supplier_id_wb": 31460,
            "take": 50,
            "skip": 0,
            "order": "desc",
            "nm_id": 123456789,
            "is_answered": False,
        },
        "json": None,
        "requires_supplier": True,
    }
    assert average == {
        "path": "/feedbacks/average_valuation",
        "method": "POST",
        "params": {"supplier_id_wb": 31460},
        "json": [123456789, 987654321],
        "requires_supplier": True,
    }


def test_generic_wb_api_routes_are_supplier_scoped_and_bounded() -> None:
    capabilities = build_gateway_request(
        operation="wb_api_capabilities",
        supplier_id_wb=31460,
    )
    operation = build_gateway_request(
        operation="wb_api_operation",
        supplier_id_wb=31460,
        payload={
            "operation_id": "stats.orders",
            "payload": {"date_from": "2026-08-01", "date_to": "2026-08-24"},
        },
    )

    assert capabilities == {
        "path": "/suppliers/31460/wb/capabilities",
        "method": "GET",
        "params": {},
        "json": None,
        "requires_supplier": True,
    }
    assert operation == {
        "path": "/suppliers/31460/wb/operations/stats.orders",
        "method": "POST",
        "params": {},
        "json": {"payload": {"date_from": "2026-08-01", "date_to": "2026-08-24"}},
        "requires_supplier": True,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"take": 501},
        {"skip": -1},
        {"order": "newest"},
        {"is_answered": "false"},
    ],
)
def test_feedback_operation_rejects_unbounded_or_ambiguous_inputs(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="proxy_payload_invalid"):
        build_gateway_request(
            operation="feedbacks",
            supplier_id_wb=31460,
            payload=payload,
        )


@pytest.mark.parametrize(
    "operation, payload",
    [
        ("wb_api_capabilities", {"payload": {}}),
        ("wb_api_operation", {"operation_id": "Stats.Orders", "payload": {}}),
        ("wb_api_operation", {"operation_id": "stats/orders", "payload": {}}),
        ("wb_api_operation", {"operation_id": "stats.orders"}),
        ("wb_api_operation", {"operation_id": "stats.orders", "payload": {"method": "GET"}}),
    ],
)
def test_generic_wb_api_routes_reject_untrusted_controls(
    operation: str, payload: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="proxy_payload_invalid|proxy_payload_not_allowed"):
        build_gateway_request(
            operation=operation,
            supplier_id_wb=31460,
            payload=payload,
        )
