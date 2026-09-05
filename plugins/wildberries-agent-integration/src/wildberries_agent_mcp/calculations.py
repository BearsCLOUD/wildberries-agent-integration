from __future__ import annotations

from math import ceil, floor, isfinite, sqrt
from statistics import mean, median
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
        recommended = max(target_stock - current_stock, 0) if sales_amount > 0 else deficit
        district_rows = row.get("deficit_districts") or []
        size = str(row.get("size") or "").strip()
        matching_stocks = stock_by_nm.get(nm_id, [])
        if size:
            matching_stocks = [
                stock for stock in matching_stocks
                if str(stock.get("size", stock.get("techSize", ""))).strip() == size
            ]
        warehouses = _allocate(
            quantity=recommended,
            rows=matching_stocks,
            district_rows=district_rows,
        )
        items.append(
            {
                "nm_id": nm_id,
                "size": size or None,
                "recommended_qty": recommended,
                "current_stock": current_stock,
                "supplier_stock": supplier_stock,
                "daily_sales_estimate": round(daily_sales, 2),
                "target_stock": target_stock,
                "seller_deficit": deficit,
                "destinations": warehouses,
                "district_demand": _compact_districts(district_rows),
                "warnings": _warnings(
                    recommended=recommended,
                    has_warehouse_data=bool(matching_stocks),
                    has_district_data=bool(district_rows),
                ),
            }
        )

    return {
        "items": items,
        "forecast_period_days": horizon_days,
        "safety_days": safety_days,
        "baseline": "Расчёт дефицита Seller основан на спросе за последние 30 дней.",
        "method": "При известных продажах: max(target_stock - current_stock, 0); иначе используется дефицит Seller.",
    }


def replenishment_math(
    *,
    daily_sales: float,
    current_stock: int,
    target_days: int,
    safety_days: int,
    inbound_qty: int = 0,
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
        "assumptions": [
            "Спрос считается постоянным и равным средним дневным продажам.",
            "Количество округляется вверх до целых единиц.",
        ],
    }


def competitive_price_analysis(
    *,
    seller_price: float | None,
    competitor_prices: list[float],
    target_position: str = "median",
    cost_price: float | None = None,
    target_margin_percent: float | None = None,
) -> dict[str, Any]:
    """Compare a seller price with a robust competitor price corridor."""
    if seller_price is not None:
        _positive_finite("seller_price", seller_price)
    if target_position not in {"low", "median", "high"}:
        raise ValueError("target_position must be one of: low, median, high")
    if cost_price is not None:
        _non_negative_finite("cost_price", cost_price)
    if target_margin_percent is not None:
        if cost_price is None:
            raise ValueError("cost_price is required with target_margin_percent")
        if not 0 <= target_margin_percent < 100:
            raise ValueError("target_margin_percent must be between 0 and 100")

    minimum_viable_price = None
    if cost_price is not None:
        margin_rate = (target_margin_percent or 0.0) / 100
        minimum_viable_price = cost_price / (1 - margin_rate)

    prices = sorted(
        price
        for value in competitor_prices
        if (price := _as_finite_float(value)) is not None and price > 0
    )
    excluded_count = len(competitor_prices) - len(prices)
    if not prices:
        return {
            "seller_price": round(seller_price, 2)
            if seller_price is not None
            else None,
            "competitor_count": 0,
            "excluded_count": excluded_count,
            "price_corridor": None,
            "position": "insufficient_data",
            "difference_to_median_percent": None,
            "corridor_target_price": None,
            "minimum_viable_price": round(minimum_viable_price, 2)
            if minimum_viable_price is not None
            else None,
            "target_price": round(minimum_viable_price, 2)
            if minimum_viable_price is not None
            else None,
            "target_position": target_position,
            "caveat": "No valid competitor prices were available; no price conclusion was made.",
        }

    low = _percentile(prices, 0.25)
    middle = float(median(prices))
    high = _percentile(prices, 0.75)
    position = "not_provided"
    if seller_price is not None:
        position = "within_corridor"
        if seller_price < low:
            position = "below_corridor"
        elif seller_price > high:
            position = "above_corridor"
    target_prices = {"low": low, "median": middle, "high": high}
    corridor_target = target_prices[target_position]
    target_price = max(corridor_target, minimum_viable_price or 0.0)

    return {
        "seller_price": round(seller_price, 2) if seller_price is not None else None,
        "competitor_count": len(prices),
        "excluded_count": excluded_count,
        "minimum_price": round(prices[0], 2),
        "maximum_price": round(prices[-1], 2),
        "average_price": round(mean(prices), 2),
        "median_price": round(middle, 2),
        "price_corridor": {
            "low": round(low, 2),
            "high": round(high, 2),
            "method": "25–75-й перцентили корректных положительных цен конкурентов",
        },
        "position": position,
        "difference_to_median_percent": round((seller_price - middle) / middle * 100, 2)
        if seller_price is not None
        else None,
        "corridor_target_price": round(corridor_target, 2),
        "minimum_viable_price": round(minimum_viable_price, 2)
        if minimum_viable_price is not None
        else None,
        "target_price": round(target_price, 2),
        "target_position": target_position,
        "caveat": (
            "Коридор описывает выборку цен, а не спрос или прибыльность. "
            "Нижняя граница по себестоимости не учитывает комиссии, логистику, налоги и другие расходы. "
            "Перед изменением цены проверьте все расходы, остатки и сопоставимость конкурентов."
        ),
    }


def competitor_analysis(
    *,
    competitor_rows: list[dict[str, Any]],
    seller_price: float | None = None,
    target_position: str = "median",
    cost_price: float | None = None,
    target_margin_percent: float | None = None,
) -> dict[str, Any]:
    """Extract common price fields and aggregate competitor rows."""
    price_fields = (
        "price",
        "discounted_price",
        "discountedPrice",
        "price_with_discount",
        "priceWithDisc",
        "sale_price",
        "salePrice",
    )
    prices: list[float] = []
    malformed_rows = 0
    matched_products: list[dict[str, int | float]] = []
    for row in competitor_rows:
        if not isinstance(row, dict):
            malformed_rows += 1
            continue
        value = next(
            (row.get(key) for key in price_fields if row.get(key) is not None),
            None,
        )
        price = _as_finite_float(value)
        if price is None or price <= 0:
            malformed_rows += 1
            continue
        prices.append(price)
        nm_id = row.get("nm_id")
        if isinstance(nm_id, int) and not isinstance(nm_id, bool) and nm_id > 0:
            matched_products.append({"nm_id": nm_id, "price": price})

    result = competitive_price_analysis(
        seller_price=seller_price,
        competitor_prices=prices,
        target_position=target_position,
        cost_price=cost_price,
        target_margin_percent=target_margin_percent,
    )
    result["source_row_count"] = len(competitor_rows)
    result["malformed_row_count"] = malformed_rows
    result["competitors"] = matched_products[:20]
    result["competitors_omitted"] = max(0, len(matched_products) - 20)
    return result


def aggregate_sales_by_region(*, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate already-observed sales rows by region without external lookups."""
    grouped: dict[str, dict[str, float | int | str]] = {}
    skipped_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            skipped_rows += 1
            continue
        region = (
            _first_text(
                row,
                "region",
                "region_name",
                "regionName",
                "oblast",
                "oblastOkrugName",
            )
            or "Unknown"
        )
        sales = _first_number(
            row, "sales", "sales_count", "orders", "quantity", "amount_sales"
        )
        revenue = _first_number(
            row,
            "revenue",
            "revenue_amount",
            "sale_amount",
            "finishedPrice",
            "priceWithDisc",
            "total_price",
            "totalPrice",
            "amount_sales_rub",
        )
        if sales is None and revenue is None:
            skipped_rows += 1
            continue
        bucket = grouped.setdefault(
            region,
            {"region": region, "sales": 0.0, "revenue": 0.0, "row_count": 0},
        )
        bucket["sales"] = float(bucket["sales"]) + (sales if sales is not None else 1.0)
        bucket["revenue"] = float(bucket["revenue"]) + (revenue or 0.0)
        bucket["row_count"] = int(bucket["row_count"]) + 1

    total_sales = sum(float(bucket["sales"]) for bucket in grouped.values())
    total_revenue = sum(float(bucket["revenue"]) for bucket in grouped.values())
    regions = []
    for bucket in grouped.values():
        sales = float(bucket["sales"])
        revenue = float(bucket["revenue"])
        regions.append(
            {
                "region": bucket["region"],
                "sales": _round_count(sales),
                "revenue": round(revenue, 2),
                "row_count": bucket["row_count"],
                "sales_share_percent": round(sales / total_sales * 100, 2)
                if total_sales
                else 0.0,
                "revenue_share_percent": round(revenue / total_revenue * 100, 2)
                if total_revenue
                else 0.0,
            }
        )
    regions.sort(
        key=lambda item: (-item["revenue"], -item["sales"], str(item["region"]))
    )

    return {
        "regions": regions,
        "totals": {
            "sales": _round_count(total_sales),
            "revenue": round(total_revenue, 2),
            "region_count": len(regions),
        },
        "source_row_count": len(rows),
        "skipped_row_count": skipped_rows,
        "assumption": (
            "Rows are treated as supplied sales facts; refunds, cancellations, and regional "
            "aliases must be normalized by the caller when they are separate records."
        ),
    }


def weather_sales_impact(*, observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate the linear relationship between temperature and observed sales."""
    pairs: list[tuple[float, float]] = []
    for row in observations:
        if not isinstance(row, dict):
            continue
        temperature = _first_number(row, "temperature", "temperature_c", "temp_c")
        sales = _first_number(row, "sales", "sales_count", "orders", "revenue")
        if temperature is not None and sales is not None:
            pairs.append((temperature, sales))

    caveat = (
        "Correlation does not establish that weather caused sales changes. Seasonality, "
        "promotions, price, stock availability, region mix, and other confounders may explain "
        "the relationship."
    )
    if len(pairs) < 4:
        return {
            "status": "insufficient_data",
            "observation_count": len(pairs),
            "correlation": None,
            "direction": "unknown",
            "strength": "unknown",
            "caveat": caveat,
        }

    temperatures = [pair[0] for pair in pairs]
    sales_values = [pair[1] for pair in pairs]
    correlation = _pearson_correlation(temperatures, sales_values)
    if correlation is None:
        return {
            "status": "insufficient_variation",
            "observation_count": len(pairs),
            "correlation": None,
            "direction": "unknown",
            "strength": "unknown",
            "caveat": caveat,
        }

    absolute = abs(correlation)
    strength = "negligible"
    if absolute >= 0.6:
        strength = "strong"
    elif absolute >= 0.4:
        strength = "moderate"
    elif absolute >= 0.2:
        strength = "weak"
    direction = "none"
    if correlation >= 0.05:
        direction = "positive"
    elif correlation <= -0.05:
        direction = "negative"

    return {
        "status": "observed_correlation",
        "observation_count": len(pairs),
        "correlation": round(correlation, 3),
        "direction": direction,
        "strength": strength,
        "caveat": caveat,
    }


def seo_score(
    *,
    title: str,
    description: str,
    keywords: list[str],
    characteristics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a transparent, deterministic product-card SEO heuristic."""
    clean_title = " ".join(str(title).split())
    clean_description = " ".join(str(description).split())
    clean_keywords = list(
        dict.fromkeys(
            keyword.casefold().strip()
            for keyword in keywords
            if isinstance(keyword, str) and keyword.strip()
        )
    )
    title_length = len(clean_title)
    description_length = len(clean_description)

    if 20 <= title_length <= 60:
        title_length_score = 25
    elif 10 <= title_length <= 80:
        title_length_score = 15
    else:
        title_length_score = 5 if title_length else 0
    if 80 <= description_length <= 1000:
        description_score = 20
    elif description_length >= 40:
        description_score = 12
    else:
        description_score = 5 if description_length else 0
    title_matches = sum(
        _contains_phrase(clean_title, keyword) for keyword in clean_keywords
    )
    description_matches = sum(
        _contains_phrase(clean_description, keyword) for keyword in clean_keywords
    )
    keyword_count = len(clean_keywords)
    title_keyword_score = (
        round(20 * title_matches / keyword_count) if keyword_count else 0
    )
    description_keyword_score = (
        round(15 * description_matches / keyword_count) if keyword_count else 0
    )
    filled_characteristics = sum(
        value is not None and (not isinstance(value, str) or bool(value.strip()))
        for value in (characteristics or {}).values()
    )
    characteristics_score = min(20, filled_characteristics * 5)
    penalty = 0
    if clean_keywords and any(
        clean_title.casefold().count(keyword) > 2 for keyword in clean_keywords
    ):
        penalty = 5

    breakdown = {
        "title_length": title_length_score,
        "description_length": description_score,
        "keywords_in_title": title_keyword_score,
        "keywords_in_description": description_keyword_score,
        "characteristics": characteristics_score,
        "keyword_stuffing_penalty": -penalty,
    }
    score = max(0, min(100, sum(breakdown.values())))
    suggestions = []
    if not 20 <= title_length <= 60:
        suggestions.append("Keep the title between 20 and 60 characters.")
    if not 80 <= description_length <= 1000:
        suggestions.append("Provide an informative description of 80–1000 characters.")
    if keyword_count == 0:
        suggestions.append("Provide explicit target keywords for coverage scoring.")
    elif title_matches < keyword_count:
        suggestions.append(
            "Add missing target keywords to the title where they read naturally."
        )
    if filled_characteristics < 4:
        suggestions.append("Fill at least four relevant product characteristics.")
    if penalty:
        suggestions.append("Reduce repeated keywords in the title.")

    return {
        "score": score,
        "max_score": 100,
        "breakdown": breakdown,
        "metrics": {
            "title_length": title_length,
            "description_length": description_length,
            "keyword_count": keyword_count,
            "keywords_in_title": title_matches,
            "keywords_in_description": description_matches,
            "filled_characteristics": filled_characteristics,
        },
        "suggestions": suggestions,
        "caveat": (
            "This is a content-completeness heuristic, not a prediction of Wildberries search "
            "ranking; marketplace algorithms and query demand are not observed."
        ),
    }


def _allocate(
    *,
    quantity: int,
    rows: list[dict[str, Any]],
    district_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if quantity <= 0:
        return []
    stock_totals: dict[str, int] = {}
    for row in rows:
        name = str(
            row.get("warehouseName", row.get("warehouse_name", "Unknown warehouse"))
        )
        qty = _as_int(row.get("quantity", row.get("qty"))) or 0
        stock_totals[name] = stock_totals.get(name, 0) + max(0, qty)
    grouped = list(stock_totals.items())
    if grouped:
        weights = [1 / (qty + 1) for _, qty in grouped]
        allocated = _weighted_units(quantity, weights)
        return [
            {
                "warehouse": name,
                "destination_type": "warehouse",
                "current_stock": qty,
                "quantity": units,
                "reason": "Больше товара направляется на склады с меньшим текущим остатком.",
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
                "reason": "Распределено по региональному спросу; остатки по складам недоступны.",
            }
            for (name, current_stock, _), units in zip(
                districts, allocated, strict=True
            )
            if units > 0
        ]
    return [
        {
            "warehouse": "unassigned",
            "destination_type": "unknown",
            "quantity": quantity,
            "reason": "Данные по складам и региональному спросу недоступны.",
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


def _warnings(
    *, recommended: int, has_warehouse_data: bool, has_district_data: bool
) -> list[str]:
    warnings = []
    if not has_warehouse_data and recommended > 0 and has_district_data:
        warnings.append(
            "Остатки по складам недоступны; направления приблизительно оценены по региональному спросу."
        )
    elif not has_warehouse_data and recommended > 0:
        warnings.append(
            "Остатки по складам недоступны; направление поставки не определено."
        )
    if not has_district_data:
        warnings.append(
            "Региональный спрос недоступен; распределение приблизительно выравнивает обеспеченность остатками."
        )
    if recommended == 0:
        warnings.append("По полученным исходным данным пополнение не требуется.")
    return warnings


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _as_finite_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _first_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in row:
            continue
        value = _as_finite_float(row[key])
        if value is not None:
            return value
    return None


def _first_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * fraction
    lower = floor(index)
    upper = ceil(index)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _pearson_correlation(left: list[float], right: list[float]) -> float | None:
    left_mean = mean(left)
    right_mean = mean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_variance = sum((value - left_mean) ** 2 for value in left)
    right_variance = sum((value - right_mean) ** 2 for value in right)
    denominator = sqrt(left_variance * right_variance)
    if denominator == 0:
        return None
    return numerator / denominator


def _round_count(value: float) -> int | float:
    return int(value) if value.is_integer() else round(value, 2)


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase in text.casefold()


def _positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _positive_finite(name: str, value: float) -> None:
    converted = _as_finite_float(value)
    if converted is None or converted <= 0:
        raise ValueError(f"{name} must be a finite number greater than zero")


def _non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _non_negative_finite(name: str, value: float) -> None:
    converted = _as_finite_float(value)
    if converted is None or converted < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _percent(name: str, value: float) -> None:
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100")
