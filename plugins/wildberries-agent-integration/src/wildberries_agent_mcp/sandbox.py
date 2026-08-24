"""Deterministic, fully virtual reviewer data for the public MCP.

The reviewer bearer is intentionally public and non-secret.  It is a fixed
demo mode, not a Seller credential: no identity bridge, gateway, database, or
Wildberries request may be reached while it is active.
"""

from __future__ import annotations

from typing import Any

SANDBOX_ACCESS_TOKEN = "wb-agent-sandbox-token-v1"
SANDBOX_SUPPLIER_ID = 900000001
SANDBOX_SOURCE = "virtual_sandbox"

# POST operations and the generic WB operation endpoint are not exposed by
# the sandbox proxy.  The public reviewer path remains read-only there.
SANDBOX_READ_OPERATIONS = frozenset(
    {
        "competitor_cards",
        "competitor_orders",
        "card_details",
        "card_photos",
        "price_block",
        "feedbacks",
        "feedback_average",
        "wb_api_capabilities",
        "seller_tape",
        "analytics_refresh_status",
        "promotion_list",
    }
)


def is_sandbox_authorization(authorization: str | None) -> bool:
    return authorization == f"Bearer {SANDBOX_ACCESS_TOKEN}"


def result(operation: str, *, data: Any = None, supplier_id_wb: int | None = None, **fields: Any) -> dict[str, Any]:
    response: dict[str, Any] = {
        "ok": True,
        "sandbox": True,
        "synthetic": True,
        "identity": "reviewer-sandbox",
        "source": SANDBOX_SOURCE,
        "operation": operation,
        "supplier_id_wb": SANDBOX_SUPPLIER_ID,
    }
    if supplier_id_wb is not None:
        response["supplier_id_wb"] = supplier_id_wb
    if data is not None:
        response["data"] = data
    response.update(fields)
    return response


def error(code: str, message: str, *, supplier_id_wb: int | None = None) -> dict[str, Any]:
    response = result("sandbox")
    response["ok"] = False
    response["error"] = {"code": code, "message": message}
    if supplier_id_wb is not None and supplier_id_wb != SANDBOX_SUPPLIER_ID:
        response["requested_supplier_id_wb"] = supplier_id_wb
    return response


def require_supplier(supplier_id_wb: int) -> dict[str, Any] | None:
    if supplier_id_wb != SANDBOX_SUPPLIER_ID:
        return error(
            "sandbox_supplier_required",
            f"В виртуальной песочнице доступен только synthetic supplier_id_wb={SANDBOX_SUPPLIER_ID}.",
            supplier_id_wb=supplier_id_wb,
        )
    return None


def suppliers() -> dict[str, Any]:
    return result(
        "list_suppliers",
        data={
            "suppliers": [
                {
                    "supplier_id_wb": SANDBOX_SUPPLIER_ID,
                    "name": "Виртуальный поставщик Wildberries",
                    "status": "connected",
                }
            ]
        },
    )


def connect_supplier() -> dict[str, Any]:
    return result(
        "connect_supplier",
        status="simulated",
        message="Виртуальный поставщик уже подключён; реальный токен не запрашивается.",
        supplier_id_wb=SANDBOX_SUPPLIER_ID,
    )


def analytics_summary(
    *, supplier_id_wb: int, period: dict[str, str], include_finance: bool, include_price_table: bool
) -> dict[str, Any]:
    response = result(
        "analytics_summary",
        supplier_id_wb=supplier_id_wb,
        period=period,
        sales_orders={
            "orders": 42,
            "units_sold": 38,
            "returns": 3,
            "revenue": 45600.0,
        },
    )
    if include_finance:
        response["finance"] = {
            "revenue": 45600.0,
            "commission": 9120.0,
            "logistics": 2280.0,
        }
    if include_price_table:
        response["price_table"] = {
            "nm_id": 900000101,
            "price": 1200.0,
            "discount_percent": 10.0,
        }
    return response


def proxy(*, supplier_id_wb: int, operation: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    if operation not in SANDBOX_READ_OPERATIONS:
        return error(
            "sandbox_operation_not_allowed",
            "В виртуальной песочнице доступны только разрешённые операции чтения.",
            supplier_id_wb=supplier_id_wb,
        )
    rows: Any
    if operation == "seller_tape":
        rows = [{"nm_id": payload.get("nm_id", 900000101), "region_name": "Москва", "orders": 12}]
    elif operation == "feedbacks":
        rows = [{"nm_id": 900000101, "rating": 5, "text": "Синтетический отзыв для проверки MCP."}]
    elif operation == "feedback_average":
        rows = {"nm_id": 900000101, "average_rating": 4.8, "reviews": 25}
    elif operation == "promotion_list":
        rows = [{"promotion_id": 1, "name": "Синтетическая акция", "status": "active"}]
    elif operation == "analytics_refresh_status":
        rows = {"status": "completed", "updated_at": "2026-01-15T12:00:00Z"}
    else:
        rows = {"items": [], "note": "Синтетическая выборка без обращения к Wildberries."}
    return result("wildberries_proxy", supplier_id_wb=supplier_id_wb, operation_id=operation, data=rows)


def warehouse_stock(*, supplier_id_wb: int, nm_ids: list[int], include_fbs_stocks: bool) -> dict[str, Any]:
    rows = [
        {
            "nm_id": nm_id,
            "warehouse": "Коледино",
            "available": 24,
            "reserved": 2,
            "fbs": 6 if include_fbs_stocks else 0,
        }
        for nm_id in nm_ids
    ]
    return result("warehouse_stock", supplier_id_wb=supplier_id_wb, data=rows)


def refresh(*, supplier_id_wb: int, period: int) -> dict[str, Any]:
    return result(
        "analytics_refresh",
        supplier_id_wb=supplier_id_wb,
        period=period,
        status="simulated",
        data={
            "task_id": f"sandbox-refresh-{supplier_id_wb}-{period}",
            "status": "queued",
        },
    )


def upload_cost_price(*, supplier_id_wb: int, nm_id: int, cost_price: float) -> dict[str, Any]:
    return result(
        "set_cost_price",
        supplier_id_wb=supplier_id_wb,
        nm_id=nm_id,
        cost_price=cost_price,
        status="simulated",
        mutation="none",
        message="Синтетическая запись: Seller и Wildberries не изменены.",
    )


def regional_sales(*, supplier_id_wb: int, period: dict[str, str], nm_id: int | None) -> list[dict[str, Any]]:
    return [
        {"date": period["date_to"], "region": "Москва", "nm_id": nm_id or 900000101, "sales": 12},
        {"date": period["date_to"], "region": "Казань", "nm_id": nm_id or 900000101, "sales": 7},
    ]


def inventory_inputs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [{"nm_id": 900000101, "amount": 20, "qty": 0, "deficit": 20, "deficit_districts": []}],
        [{"nmId": 900000101, "warehouseName": "Коледино", "quantity": 24}],
    )
