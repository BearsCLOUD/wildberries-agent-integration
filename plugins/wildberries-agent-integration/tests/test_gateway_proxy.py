from __future__ import annotations

import pytest

from wildberries_agent_mcp.gateway_proxy import (
    allowed_operations,
    build_gateway_request,
)


def test_gateway_operations_are_fixed_and_read_only() -> None:
    assert allowed_operations() == (
        "competitor_cards",
        "competitor_orders",
        "card_details",
        "card_photos",
        "price_block",
        "seller_tape",
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
