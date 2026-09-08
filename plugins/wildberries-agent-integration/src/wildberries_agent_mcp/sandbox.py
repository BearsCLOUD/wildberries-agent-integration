"""Deterministic, fully virtual reviewer data for the public MCP.

The reviewer bearer is intentionally public and non-secret.  It is a fixed
demo mode, not a Seller credential: no Seller Gateway, database, or
Wildberries request may be reached while it is active.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

SANDBOX_ACCESS_TOKEN = "wb-agent-sandbox-token-v1"
SANDBOX_SUPPLIER_ID = 900000001
SANDBOX_SOURCE = "virtual_sandbox"
SANDBOX_RESOURCE = "https://wb.seller.bears.ru/mcp"
_COST_CONFIRMATION_TTL_SECONDS = 300


@dataclass(slots=True)
class _CostConfirmation:
    identity: str
    resource: str
    supplier_id_wb: int
    nm_id: int
    cost_price: str
    expires_at: float
    state: str = "prepared"
    completed_result: dict[str, Any] | None = None


_cost_confirmations: dict[str, _CostConfirmation] = {}
_cost_confirmation_lock = threading.Lock()

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


def result(
    operation: str,
    *,
    data: Any = None,
    supplier_id_wb: int | None = None,
    **fields: Any,
) -> dict[str, Any]:
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


def error(
    code: str, message: str, *, supplier_id_wb: int | None = None
) -> dict[str, Any]:
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


def connect_supplier(*, supplier_id_wb: int | None = None) -> dict[str, Any]:
    response = result(
        "connect_supplier",
        status="connected",
        supplier_id_wb=SANDBOX_SUPPLIER_ID,
    )
    if supplier_id_wb is not None and supplier_id_wb != SANDBOX_SUPPLIER_ID:
        response["requested_supplier_id_wb"] = supplier_id_wb
    return response


def connection_status() -> dict[str, Any]:
    return result("connection_status", status="connected")


def connect_telegram() -> dict[str, Any]:
    return result("connect_telegram", status="connected")


def analytics_summary(
    *,
    supplier_id_wb: int,
    period: dict[str, str],
    include_finance: bool,
    include_price_table: bool,
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


def proxy(
    *, supplier_id_wb: int, operation: str, payload: dict[str, Any] | None
) -> dict[str, Any]:
    payload = payload or {}
    if operation not in SANDBOX_READ_OPERATIONS:
        return error(
            "sandbox_operation_not_allowed",
            "В виртуальной песочнице доступны только разрешённые операции чтения.",
            supplier_id_wb=supplier_id_wb,
        )
    rows: Any
    if operation == "seller_tape":
        rows = [
            {
                "nm_id": payload.get("nm_id", 900000101),
                "region_name": "Москва",
                "orders": 12,
            }
        ]
    elif operation == "feedbacks":
        rows = [
            {
                "nm_id": 900000101,
                "rating": 5,
                "text": "Синтетический отзыв для проверки MCP.",
            }
        ]
    elif operation == "feedback_average":
        rows = {"nm_id": 900000101, "average_rating": 4.8, "reviews": 25}
    elif operation == "promotion_list":
        rows = [{"promotion_id": 1, "name": "Синтетическая акция", "status": "active"}]
    elif operation == "analytics_refresh_status":
        rows = {"status": "completed", "updated_at": "2026-01-15T12:00:00Z"}
    else:
        rows = {
            "items": [],
            "note": "Синтетическая выборка без обращения к Wildberries.",
        }
    return result(
        "wildberries_proxy",
        supplier_id_wb=supplier_id_wb,
        operation_id=operation,
        data=rows,
    )


def warehouse_stock(
    *, supplier_id_wb: int, nm_ids: list[int], include_fbs_stocks: bool
) -> dict[str, Any]:
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


def prepare_cost_price(
    *,
    supplier_id_wb: int,
    nm_id: int,
    cost_price: float,
    identity: str = "reviewer-sandbox",
    resource: str = SANDBOX_RESOURCE,
) -> dict[str, Any]:
    token = secrets.token_urlsafe(32)
    token_hash = _confirmation_hash(token)
    with _cost_confirmation_lock:
        now = time.monotonic()
        expired = [
            key
            for key, record in _cost_confirmations.items()
            if record.expires_at <= now
        ]
        for key in expired:
            _cost_confirmations.pop(key, None)
        _cost_confirmations[token_hash] = _CostConfirmation(
            identity=identity,
            resource=resource,
            supplier_id_wb=supplier_id_wb,
            nm_id=nm_id,
            cost_price=_canonical_cost(cost_price),
            expires_at=now + _COST_CONFIRMATION_TTL_SECONDS,
        )
    response = _cost_confirmation_error(
        "confirmation_required",
        "Покажите точные параметры пользователю и запросите отдельное подтверждение записи.",
        supplier_id_wb=supplier_id_wb,
    )
    response.update(
        {
            "operation": "set_cost_price_preview",
            "requested": {
                "supplier_id_wb": supplier_id_wb,
                "nm_id": nm_id,
                "cost_price": cost_price,
            },
            "confirmation_token": token,
            "expires_in": _COST_CONFIRMATION_TTL_SECONDS,
        }
    )
    return response


def upload_cost_price(
    *,
    supplier_id_wb: int,
    nm_id: int,
    cost_price: float,
    confirmation_token: str | None,
    identity: str = "reviewer-sandbox",
    resource: str = SANDBOX_RESOURCE,
) -> dict[str, Any]:
    if not confirmation_token:
        return _cost_confirmation_error(
            "confirmation_required",
            "Сначала получите preview и confirmation_token с confirm=false.",
            supplier_id_wb=supplier_id_wb,
        )

    token_hash = _confirmation_hash(confirmation_token)
    with _cost_confirmation_lock:
        record = _cost_confirmations.get(token_hash)
        if record is None or record.expires_at <= time.monotonic():
            _cost_confirmations.pop(token_hash, None)
            return _cost_confirmation_error(
                "confirmation_expired",
                "Подтверждение отсутствует или истекло. Получите новый preview.",
                supplier_id_wb=supplier_id_wb,
            )
        if (
            record.identity != identity
            or record.resource != resource
            or record.supplier_id_wb != supplier_id_wb
            or record.nm_id != nm_id
            or record.cost_price != _canonical_cost(cost_price)
        ):
            return _cost_confirmation_error(
                "confirmation_mismatch",
                "Параметры отличаются от preview. Получите новое подтверждение.",
                supplier_id_wb=supplier_id_wb,
            )
        if record.state == "completed" and record.completed_result is not None:
            return dict(record.completed_result)
        if record.state != "prepared":
            return _sandbox_unknown_write_status(supplier_id_wb)
        record.state = "in_flight"

    try:
        completed = _simulated_cost_result(
            supplier_id_wb=supplier_id_wb,
            nm_id=nm_id,
            cost_price=cost_price,
        )
    except Exception:  # noqa: BLE001 - any uncertain simulated completion must fail closed
        with _cost_confirmation_lock:
            record.state = "unknown"
        return _sandbox_unknown_write_status(supplier_id_wb)

    with _cost_confirmation_lock:
        record.state = "completed"
        record.completed_result = dict(completed)
    return completed


def _simulated_cost_result(
    *, supplier_id_wb: int, nm_id: int, cost_price: float
) -> dict[str, Any]:
    return result(
        "set_cost_price",
        supplier_id_wb=supplier_id_wb,
        nm_id=nm_id,
        cost_price=cost_price,
        status="simulated",
        mutation="none",
        message="Синтетическая запись: Seller и Wildberries не изменены.",
    )


def _cost_confirmation_error(
    code: str, message: str, *, supplier_id_wb: int
) -> dict[str, Any]:
    response = result(
        "set_cost_price",
        supplier_id_wb=supplier_id_wb,
    )
    response["ok"] = False
    response["error"] = {"code": code, "message": message}
    return response


def _sandbox_unknown_write_status(supplier_id_wb: int) -> dict[str, Any]:
    response = _cost_confirmation_error(
        "write_status_unknown",
        "Статус записи неизвестен; автоматический повтор запрещён.",
        supplier_id_wb=supplier_id_wb,
    )
    response["write_status"] = "possibly_applied"
    return response


def _confirmation_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _canonical_cost(cost_price: float) -> str:
    return "0.0" if cost_price == 0 else repr(cost_price)


def regional_sales(
    *, supplier_id_wb: int, period: dict[str, str], nm_id: int | None
) -> list[dict[str, Any]]:
    return [
        {
            "date": period["date_to"],
            "region": "Москва",
            "nm_id": nm_id or 900000101,
            "sales": 12,
        },
        {
            "date": period["date_to"],
            "region": "Казань",
            "nm_id": nm_id or 900000101,
            "sales": 7,
        },
    ]


def weather_inputs(
    *, period: dict[str, str], region: str | None, nm_id: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return matching deterministic sales and weather rows for reviewer calls."""
    start = date.fromisoformat(period["date_from"])
    end = date.fromisoformat(period["date_to"])
    sample_start = max(start, end - timedelta(days=13))
    selected_region = region.strip() if region and region.strip() else "Екатеринбург"
    sales_rows: list[dict[str, Any]] = []
    weather_rows: list[dict[str, Any]] = []
    current = sample_start
    index = 0
    while current <= end:
        sales_rows.append(
            {
                "date": current.isoformat(),
                "region": selected_region,
                "nm_id": nm_id,
                "sales": 5 + index,
            }
        )
        weather_rows.append(
            {
                "date": current.isoformat(),
                "region": selected_region,
                "temperature_c": 12 + index,
            }
        )
        current += timedelta(days=1)
        index += 1
    return sales_rows, weather_rows


def inventory_inputs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return (
        [
            {
                "nm_id": 900000101,
                "amount": 20,
                "qty": 0,
                "deficit": 20,
                "deficit_districts": [],
            }
        ],
        [{"nmId": 900000101, "warehouseName": "Коледино", "quantity": 24}],
    )
