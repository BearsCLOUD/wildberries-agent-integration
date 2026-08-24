from __future__ import annotations

from math import ceil, floor
from typing import Any


def unit_economics(
    *,
    price: float,
    cost_price: float,
    commission_percent: float,
    logistics_per_unit: float = 0.0,
    storage_per_unit: float = 0.0,
    advertising_per_unit: float = 0.0,
    tax_percent: float = 0.0,
    other_costs_per_unit: float = 0.0,
    discount_percent: float = 0.0,
    target_margin_percent: float | None = None,
) -> dict[str, Any]:
    _positive("price", price)
    _non_negative("cost_price", cost_price)
    _non_negative("logistics_per_unit", logistics_per_unit)
    _non_negative("storage_per_unit", storage_per_unit)
    _non_negative("advertising_per_unit", advertising_per_unit)
    _non_negative("other_costs_per_unit", other_costs_per_unit)
    _percent("commission_percent", commission_percent)
    _percent("tax_percent", tax_percent)
    _percent("discount_percent", discount_percent)
    if target_margin_percent is not None:
        _percent("target_margin_percent", target_margin_percent)

    commission_rate = commission_percent / 100
    tax_rate = tax_percent / 100
    discount_rate = discount_percent / 100
    net_price = price * (1 - discount_rate)
    commission = net_price * commission_rate
    tax = net_price * tax_rate
    fixed_costs = (
        cost_price
        + logistics_per_unit
        + storage_per_unit
        + advertising_per_unit
        + other_costs_per_unit
    )
    total_costs = fixed_costs + commission + tax
    profit = net_price - total_costs
    margin = (profit / net_price * 100) if net_price else None

    variable_factor = (1 - discount_rate) * (1 - commission_rate - tax_rate)
    break_even_price = fixed_costs / variable_factor if variable_factor > 0 else None
    target_margin_price = None
    if target_margin_percent is not None:
        target_factor = 1 - commission_rate - tax_rate - target_margin_percent / 100
        if target_factor > 0 and (1 - discount_rate) > 0:
            target_margin_price = fixed_costs / ((1 - discount_rate) * target_factor)

    return {
        "inputs": {
            "price": round(price, 2),
            "cost_price": round(cost_price, 2),
            "commission_percent": commission_percent,
            "logistics_per_unit": round(logistics_per_unit, 2),
            "storage_per_unit": round(storage_per_unit, 2),
            "advertising_per_unit": round(advertising_per_unit, 2),
            "tax_percent": tax_percent,
            "other_costs_per_unit": round(other_costs_per_unit, 2),
            "discount_percent": discount_percent,
            "target_margin_percent": target_margin_percent,
        },
        "net_price": round(net_price, 2),
        "commission": round(commission, 2),
        "tax": round(tax, 2),
        "total_costs": round(total_costs, 2),
        "profit": round(profit, 2),
        "margin_percent": round(margin, 2) if margin is not None else None,
        "break_even_price": round(break_even_price, 2)
        if break_even_price is not None
        else None,
        "target_margin_price": round(target_margin_price, 2)
        if target_margin_price is not None
        else None,
        "formula": "net_price = price × (1 − discount); profit = net_price − commission − tax − fixed costs",
        "assumptions": [
            "Commission and tax are modelled as percentages of the discounted selling price.",
            "Logistics, storage, advertising, cost price, and other costs are per unit.",
            "Wildberries fees and service data can change; verify before a price write.",
        ],
    }


def inventory_forecast(
    *,
    deficit_rows: list[dict[str, Any]],
    stock_rows: list[dict[str, Any]],
    horizon_days: int,
    safety_days: int,
) -> dict[str, Any]:
    if not 1 <= horizon_days <= 365:
        raise ValueError("horizon_days must be between 1 and 365")
    if not 0 <= safety_days <= 90:
        raise ValueError("safety_days must be between 0 and 90")

    stock_by_nm: dict[int, list[dict[str, Any]]] = {}
    for row in stock_rows:
        nm_id = _as_int(row.get("nmId", row.get("nm_id")))
        if nm_id is None:
            continue
        stock_by_nm.setdefault(nm_id, []).append(row)

    items: list[dict[str, Any]] = []
    for row in deficit_rows:
        nm_id = _as_int(row.get("nm_id", row.get("nmId")))
        if nm_id is None:
            continue
        current_stock = _as_int(row.get("qty")) or 0
        supplier_stock = _as_int(row.get("qty_supplier_stock")) or 0
        deficit = max(0, _as_int(row.get("deficit")) or 0)
        sales_amount = _as_int(row.get("amount")) or 0
        daily_sales = sales_amount / 30 if sales_amount > 0 else 0.0
        target_stock = ceil(daily_sales * (horizon_days + safety_days))
        recommended = max(deficit, target_stock - current_stock, 0)
        district_rows = row.get("deficit_districts") or []
        warehouses = _allocate(
            quantity=recommended,
            rows=stock_by_nm.get(nm_id, []),
            district_rows=district_rows,
        )
        items.append(
            {
                "nm_id": nm_id,
                "recommended_qty": recommended,
                "current_stock": current_stock,
                "supplier_stock": supplier_stock,
                "daily_sales_estimate": round(daily_sales, 2),
                "target_stock": target_stock,
                "destinations": warehouses,
                "district_demand": _compact_districts(district_rows),
                "warnings": _warnings(
                    recommended=recommended,
                    has_warehouse_data=bool(stock_by_nm.get(nm_id)),
                    has_district_data=bool(district_rows),
                ),
            }
        )

    return {
        "items": items,
        "forecast_period_days": horizon_days,
        "safety_days": safety_days,
        "baseline": "Seller deficit endpoint uses a recent 30-day demand baseline.",
        "method": "recommended = max(deficit, target_stock - current_stock, 0)",
    }


def replenishment_math(
    *, daily_sales: float, current_stock: int, target_days: int, safety_days: int, inbound_qty: int = 0
) -> dict[str, Any]:
    _non_negative("daily_sales", daily_sales)
    if current_stock < 0 or inbound_qty < 0:
        raise ValueError("stock values must be non-negative")
    if target_days < 1 or target_days > 365 or safety_days < 0 or safety_days > 90:
        raise ValueError("target_days/safety_days are outside the supported range")
    target_stock = ceil(daily_sales * (target_days + safety_days))
    recommended = max(0, target_stock - current_stock - inbound_qty)
    return {
        "target_stock": target_stock,
        "recommended_qty": recommended,
        "formula": "max(0, ceil(daily_sales × (target_days + safety_days)) − current_stock − inbound_qty)",
        "assumptions": ["Demand is treated as a stable daily average.", "Round up to whole units."],
    }


def _allocate(
    *,
    quantity: int,
    rows: list[dict[str, Any]],
    district_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if quantity <= 0:
        return []
    grouped: list[tuple[str, int]] = []
    for row in rows:
        name = str(row.get("warehouseName", row.get("warehouse_name", "Unknown warehouse")))
        qty = _as_int(row.get("quantity", row.get("qty"))) or 0
        grouped.append((name, max(0, qty)))
    if grouped:
        weights = [1 / (qty + 1) for _, qty in grouped]
        allocated = _weighted_units(quantity, weights)
        return [
            {
                "warehouse": name,
                "destination_type": "warehouse",
                "current_stock": qty,
                "quantity": units,
                "reason": "balanced toward lower current stock",
            }
            for (name, qty), units in zip(grouped, allocated, strict=True)
            if units > 0
        ]

    districts: list[tuple[str, int | None, int]] = []
    for row in district_rows or []:
        if not isinstance(row, dict):
            continue
        name = row.get("district_name", row.get("district_short_name"))
        if not name:
            continue
        demand = max(
            _as_int(row.get("amount")) or 0,
            _as_int(row.get("deficit")) or 0,
        )
        districts.append((str(name), _as_int(row.get("qty")), demand))
    if districts:
        demand_total = sum(demand for _, _, demand in districts)
        weights = [demand if demand_total else 1 for _, _, demand in districts]
        allocated = _weighted_units(quantity, weights)
        return [
            {
                "warehouse": name,
                "destination_type": "district",
                "current_stock": current_stock,
                "quantity": units,
                "reason": "allocated by regional demand; warehouse stock unavailable",
            }
            for (name, current_stock, _), units in zip(districts, allocated, strict=True)
            if units > 0
        ]
    return [
        {
            "warehouse": "unassigned",
            "destination_type": "unknown",
            "quantity": quantity,
            "reason": "warehouse and regional demand data unavailable",
        }
    ]


def _weighted_units(quantity: int, weights: list[int | float]) -> list[int]:
    total_weight = sum(weights)
    if total_weight <= 0:
        return [0 for _ in weights]
    raw = [quantity * weight / total_weight for weight in weights]
    allocated = [floor(value) for value in raw]
    remainder = quantity - sum(allocated)
    for index in sorted(
        range(len(raw)), key=lambda i: raw[i] - allocated[i], reverse=True
    )[:remainder]:
        allocated[index] += 1
    return allocated


def _compact_districts(rows: list[Any]) -> list[dict[str, Any]]:
    result = []
    for row in rows[:30]:
        if not isinstance(row, dict):
            continue
        result.append(
            {
                "district": row.get("district_name", row.get("district_short_name")),
                "deficit": row.get("deficit", 0),
                "qty": row.get("qty", 0),
                "orders": row.get("amount", 0),
            }
        )
    return result


def _warnings(*, recommended: int, has_warehouse_data: bool, has_district_data: bool) -> list[str]:
    warnings = []
    if not has_warehouse_data and recommended > 0 and has_district_data:
        warnings.append(
            "Warehouse stock data is unavailable; destinations use regional demand as a heuristic."
        )
    elif not has_warehouse_data and recommended > 0:
        warnings.append("Warehouse stock data is unavailable; destination is unassigned.")
    if not has_district_data:
        warnings.append("Regional demand was unavailable; use the allocation as a coverage heuristic.")
    if recommended == 0:
        warnings.append("No replenishment is recommended from the returned baseline.")
    return warnings


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _percent(name: str, value: float) -> None:
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100")
