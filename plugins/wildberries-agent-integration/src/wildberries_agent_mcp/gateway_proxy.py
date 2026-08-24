"""Fixed Seller Gateway operations that proxy approved Wildberries calls.

The MCP surface accepts operation names only.  The gateway resolves the
user-owned Wildberries credential; callers never provide a token, host, path,
or HTTP method.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

MAX_PAYLOAD_BYTES = 16 * 1024
MAX_LIST_ITEMS = 100

_SENSITIVE_PARTS = (
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "apikey",
    "credential",
    # The public operation contract must not become an indirect URL/method proxy.
    "url",
    "uri",
    "path",
    "method",
    "header",
    "host",
)

_OPERATIONS = {
    "competitor_cards": {"path": "/open_methods/competitors", "method": "GET"},
    "competitor_orders": {"path": "/competitors/products/orders", "method": "POST"},
    "card_details": {"path": "/open_methods/get_cards_detail", "method": "POST"},
    "card_photos": {"path": "/open_methods/get_cards_photo", "method": "POST"},
    "price_block": {"path": "/open_methods/price_block", "method": "POST"},
    "seller_tape": {"path": "/statistics/tape/v2", "method": "GET", "supplier": True},
    "kt_statistics_period": {
        "path": "/integration-wb/kt/statistics/period",
        "method": "POST",
        "supplier": True,
    },
    "kt_statistics_grouped": {
        "path": "/integration-wb/kt/statistics/period/grouped",
        "method": "POST",
        "supplier": True,
    },
    "promotion_list": {
        "path": "/integration-wb/promotion",
        "method": "GET",
        "supplier": True,
    },
    "promotion_details": {
        "path": "/integration-wb/promotion",
        "method": "POST",
        "supplier": True,
    },
}


def allowed_operations() -> tuple[str, ...]:
    return tuple(_OPERATIONS)


def build_gateway_request(
    *,
    operation: str,
    supplier_id_wb: int,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one fixed gateway request or raise ``ValueError`` for bad input."""

    if operation not in _OPERATIONS:
        raise ValueError("proxy_operation_not_allowed")
    if not isinstance(supplier_id_wb, int) or isinstance(supplier_id_wb, bool) or supplier_id_wb <= 0:
        raise ValueError("invalid_proxy_supplier")
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping):
        raise ValueError("proxy_payload_invalid")
    _validate_tree(payload)

    spec = _OPERATIONS[operation]
    query: dict[str, Any] = {}
    body: dict[str, Any] | None = None
    if operation == "competitor_cards":
        query["nm_id"] = _positive_int(payload, "nm_id")
    elif operation == "competitor_orders":
        competitor_type = payload.get("competitors_type", "category_path")
        if competitor_type not in {"category_path", "supplier_id_wb", "brand"}:
            raise ValueError("proxy_payload_invalid")
        search_for = payload.get("search_for")
        if not isinstance(search_for, (str, int)) or isinstance(search_for, bool):
            raise ValueError("proxy_payload_invalid")
        if isinstance(search_for, str) and (not search_for.strip() or len(search_for) > 200):
            raise ValueError("proxy_payload_invalid")
        query["competitors_type"] = competitor_type
        body = {"search_for": search_for}
    elif operation in {"card_details", "card_photos", "price_block"}:
        nm_ids = payload.get("nm_ids")
        if (
            not isinstance(nm_ids, list)
            or not 1 <= len(nm_ids) <= MAX_LIST_ITEMS
            or any(not isinstance(item, int) or isinstance(item, bool) or item <= 0 for item in nm_ids)
        ):
            raise ValueError("proxy_payload_invalid")
        body = {"nm_ids": list(nm_ids)}
    elif operation == "seller_tape":
        query.update(
            {
                "supplier_id_wb": supplier_id_wb,
                "nm_id": _positive_int(payload, "nm_id"),
                "limit": _bounded_int(payload.get("limit", 100), 1, 1000),
                "page": _bounded_int(payload.get("page", 0), 0, 100),
            }
        )
    elif operation in {"kt_statistics_period", "kt_statistics_grouped", "promotion_details"}:
        query["supplier_id_wb"] = supplier_id_wb
        body = dict(payload)
    elif operation == "promotion_list":
        query["supplier_id_wb"] = supplier_id_wb

    return {
        "path": spec["path"],
        "method": spec["method"],
        "params": query,
        "json": body,
        "requires_supplier": bool(spec.get("supplier")),
    }


def _positive_int(payload: Mapping[str, Any], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("proxy_payload_invalid")
    return value


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError("proxy_payload_invalid")
    return value


def _validate_tree(value: Any, *, depth: int = 0) -> None:
    if depth > 6:
        raise ValueError("proxy_payload_too_deep")
    if isinstance(value, Mapping):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError("proxy_payload_too_large")
        for key, item in value.items():
            if not isinstance(key, str) or _sensitive_key(key):
                raise ValueError("proxy_payload_not_allowed")
            _validate_tree(item, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        if len(value) > MAX_LIST_ITEMS:
            raise ValueError("proxy_payload_too_large")
        for item in value:
            _validate_tree(item, depth=depth + 1)
    elif isinstance(value, str):
        if len(value) > 2_000 or any(ord(char) < 32 for char in value):
            raise ValueError("proxy_payload_invalid")
    elif value is not None and type(value) not in {bool, int, float}:
        raise ValueError("proxy_payload_invalid")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("proxy_payload_invalid") from error
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("proxy_payload_too_large")


def _sensitive_key(key: str) -> bool:
    normalized = "".join(char for char in key.casefold() if char.isalnum())
    return any(part in normalized for part in _SENSITIVE_PARTS)
