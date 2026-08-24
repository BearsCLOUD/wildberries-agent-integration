from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from .calculations import inventory_forecast, replenishment_math, unit_economics
from .client import GatewayError, SellerGatewayClient
from .config import Settings


def build_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    gateway = SellerGatewayClient(settings)
    server = FastMCP(
        name="Wildberries Agent Integration",
        instructions=(
            "Use Seller-scoped Wildberries analytics. Keep credentials out of prompts and results. "
            "Prefer the calculator and transparent replenishment forecast for decisions."
        ),
        host=settings.host,
        port=settings.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @server.custom_route("/healthz", methods=["GET"], name="healthz")
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "wildberries-agent-integration"})

    @server.tool(
        name="wb_connect_supplier",
        title="Connect a Wildberries supplier",
        description=(
            "Open the existing Seller browser flow for supplier onboarding. The user enters the "
            "Wildberries personal token outside the agent prompt; this tool never accepts or returns it."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
        ),
    )
    async def wb_connect_supplier(
        supplier_id_wb: int | None = None, ctx: Context | None = None
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if auth is not None:
            try:
                oauth = await gateway.request(
                    authorization=auth,
                    path="/wb-oauth/authorize",
                    request_id=_request_id(ctx),
                )
                if isinstance(oauth, dict):
                    authorization_url = oauth.get("authorization_url") or oauth.get("url")
                    if isinstance(authorization_url, str) and authorization_url.startswith("https://"):
                        return {
                            "ok": True,
                            "url": authorization_url,
                            "flow": "Seller WB OAuth",
                            "security": "Complete the provider consent in the browser; credentials stay outside the agent conversation.",
                        }
            except GatewayError:
                # A deployment may not expose WB OAuth yet; the explicit browser handoff remains safe.
                pass
        if not settings.connect_url:
            return {
                "ok": False,
                "error": {"code": "connect_url_not_configured", "message": "Seller onboarding URL is not configured."},
            }
        return {
            "ok": True,
            "url": _with_query(settings.connect_url, {"source": "wildberries-agent-integration", **({"supplier_id_wb": supplier_id_wb} if supplier_id_wb else {})}),
            "flow": "Integration → Add supplier → Personal API token",
            "security": "Enter the token in the Seller service, not in chat. The agent receives only connection status.",
        }

    @server.tool(
        name="wb_list_suppliers",
        title="List connected suppliers",
        description="List suppliers available to the authenticated Seller user without credentials or token values.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def wb_list_suppliers(ctx: Context) -> dict[str, Any]:
        return await _gateway_result(gateway, settings, ctx, path="/suppliers", operation="list_suppliers")

    @server.tool(
        name="wb_analytics_summary",
        title="Wildberries analytics summary",
        description="Read sales/orders and optional finance/price summaries for one supplier and a bounded date range.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    async def wb_analytics_summary(
        supplier_id_wb: int,
        date_from: str,
        date_to: str,
        include_finance: bool = True,
        include_price_table: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        try:
            period = _validate_period(date_from, date_to)
        except ValueError as error:
            return {"ok": False, "error": {"code": "invalid_period", "message": str(error)}}
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        try:
            combined = await gateway.request(
                authorization=auth,
                path="/statistics/report/combined",
                params={"supplier_id_wb": supplier_id_wb, **period},
                request_id=_request_id(ctx),
            )
            result: dict[str, Any] = {
                "ok": True,
                "supplier_id_wb": supplier_id_wb,
                "period": period,
                "sales_orders": _compact(combined),
            }
            if include_finance:
                finance = await gateway.request(
                    authorization=auth,
                    path="/financial_report/dashboard/v2",
                    params={"supplier_id_wb": supplier_id_wb, **period},
                    request_id=_request_id(ctx),
                )
                result["finance"] = _compact(finance)
            if include_price_table:
                prices = await gateway.request(
                    authorization=auth,
                    path="/price_management",
                    params={"supplier_id_wb": supplier_id_wb},
                    request_id=_request_id(ctx),
                )
                result["price_table"] = _compact(prices)
            return result
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_warehouse_stock",
        title="Wildberries warehouse stock",
        description="Read current WB warehouse stock for up to 1,000 nm IDs through the Seller gateway.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    async def wb_warehouse_stock(
        supplier_id_wb: int,
        nm_ids: list[int],
        chrt_ids: list[int] | None = None,
        include_fbs_stocks: bool = True,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if not 1 <= len(nm_ids) <= 1000:
            return {"ok": False, "error": {"code": "invalid_nm_ids", "message": "Provide between 1 and 1,000 nm IDs."}}
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        try:
            data = await gateway.request(
                authorization=auth,
                path="/price_management/stocks-report/wb-warehouses",
                method="POST",
                params={"supplier_id_wb": supplier_id_wb, "include_fbs_stocks": include_fbs_stocks},
                json={"nmIds": nm_ids, "chrtIds": chrt_ids, "limit": 250000, "offset": 0},
                request_id=_request_id(ctx),
            )
            return {"ok": True, "supplier_id_wb": supplier_id_wb, "data": _compact(data)}
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_unit_economics",
        title="Wildberries unit economics calculator",
        description="Calculate net price, commission, tax, costs, profit, margin, and break-even price from explicit inputs.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def wb_unit_economics(
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
        try:
            return {"ok": True, **unit_economics(
                price=price,
                cost_price=cost_price,
                commission_percent=commission_percent,
                logistics_per_unit=logistics_per_unit,
                storage_per_unit=storage_per_unit,
                advertising_per_unit=advertising_per_unit,
                tax_percent=tax_percent,
                other_costs_per_unit=other_costs_per_unit,
                discount_percent=discount_percent,
                target_margin_percent=target_margin_percent,
            )}
        except ValueError as error:
            return {"ok": False, "error": {"code": "invalid_calculator_input", "message": str(error)}}

    @server.tool(
        name="wb_replenishment_math",
        title="Replenishment calculator",
        description="Calculate a deterministic replenishment quantity from daily sales, stock, target days, and safety days.",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    async def wb_replenishment_math(
        daily_sales: float,
        current_stock: int,
        target_days: int,
        safety_days: int,
        inbound_qty: int = 0,
    ) -> dict[str, Any]:
        try:
            return {"ok": True, **replenishment_math(
                daily_sales=daily_sales,
                current_stock=current_stock,
                target_days=target_days,
                safety_days=safety_days,
                inbound_qty=inbound_qty,
            )}
        except ValueError as error:
            return {"ok": False, "error": {"code": "invalid_replenishment_input", "message": str(error)}}

    @server.tool(
        name="wb_inventory_forecast",
        title="Warehouse replenishment forecast",
        description=(
            "Use Seller deficit and warehouse stock data to estimate how many units to replenish and where. "
            "Return assumptions and warnings; this is a recommendation, not a sales guarantee."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True),
    )
    async def wb_inventory_forecast(
        supplier_id_wb: int,
        nm_ids: list[int] | None = None,
        horizon_days: int = 30,
        safety_days: int = 7,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if nm_ids is not None and not 1 <= len(nm_ids) <= 100:
            return {"ok": False, "error": {"code": "invalid_nm_ids", "message": "Provide 1-100 nm IDs or omit the filter."}}
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        try:
            deficits = await gateway.request(
                authorization=auth,
                path="/statistics/orders",
                params={"supplier_id_wb": supplier_id_wb},
                request_id=_request_id(ctx),
            )
            deficit_rows = deficits if isinstance(deficits, list) else deficits.get("data", []) if isinstance(deficits, dict) else []
            if nm_ids is not None:
                allowed = set(nm_ids)
                deficit_rows = [
                    row
                    for row in deficit_rows
                    if isinstance(row, dict)
                    and _as_int_value(row.get("nm_id", row.get("nmId"))) in allowed
                ]
            selected_ids = [row.get("nm_id", row.get("nmId")) for row in deficit_rows if isinstance(row, dict)]
            selected_ids = [int(value) for value in selected_ids if value is not None][:100]
            stock_rows: list[dict[str, Any]] = []
            stock_status = "not_requested"
            if selected_ids:
                try:
                    stocks = await gateway.request(
                        authorization=auth,
                        path="/price_management/stocks-report/wb-warehouses",
                        method="POST",
                        params={"supplier_id_wb": supplier_id_wb, "include_fbs_stocks": True},
                        json={"nmIds": selected_ids, "chrtIds": None, "limit": 250000, "offset": 0},
                        request_id=_request_id(ctx),
                    )
                    stock_rows = stocks.get("data", []) if isinstance(stocks, dict) else []
                    stock_status = "ok"
                except GatewayError as error:
                    stock_status = error.code
            forecast = inventory_forecast(
                deficit_rows=deficit_rows[:100],
                stock_rows=stock_rows,
                horizon_days=horizon_days,
                safety_days=safety_days,
            )
            return {
                "ok": True,
                "supplier_id_wb": supplier_id_wb,
                "warehouse_stock_status": stock_status,
                "data": _compact(forecast),
            }
        except GatewayError as error:
            return _gateway_error(error)
        except ValueError as error:
            return {"ok": False, "error": {"code": "invalid_forecast_input", "message": str(error)}}

    return server


def _auth_header(ctx: Context | None, settings: Settings) -> str | None:
    if ctx is not None:
        try:
            request_context = ctx.request_context
        except ValueError:
            request_context = None
        request = getattr(request_context, "request", None)
        headers = getattr(request, "headers", None)
        value = headers.get("authorization") if headers is not None else None
        if isinstance(value, str) and value.startswith("Bearer ") and len(value) > 7:
            return value
    if settings.allows_static_token and settings.static_access_token:
        token = settings.static_access_token
        return token if token.startswith("Bearer ") else f"Bearer {token}"
    return None


async def _gateway_result(
    gateway: SellerGatewayClient,
    settings: Settings,
    ctx: Context | None,
    *,
    path: str,
    operation: str,
) -> dict[str, Any]:
    auth = _auth_header(ctx, settings)
    if auth is None:
        return _auth_error()
    try:
        data = await gateway.request(authorization=auth, path=path, request_id=_request_id(ctx))
        return {"ok": True, "operation": operation, "data": _compact(data)}
    except GatewayError as error:
        return _gateway_error(error)


def _auth_error() -> dict[str, Any]:
    return {"ok": False, "error": {"code": "auth_required", "message": "Connect the Seller account before requesting supplier data."}}


def _gateway_error(error: GatewayError) -> dict[str, Any]:
    return {"ok": False, "error": {"code": error.code, "status": error.status}}


def _request_id(ctx: Context | None) -> str | None:
    if ctx is None:
        return None
    try:
        return ctx.request_id
    except ValueError:
        return None


def _validate_period(date_from: str, date_to: str) -> dict[str, str]:
    try:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except ValueError as error:
        raise ValueError("date_from/date_to must be ISO dates") from error
    if start > end:
        raise ValueError("date_from must not be after date_to")
    if end - start > timedelta(days=366):
        raise ValueError("date range must not exceed 366 days")
    return {"date_from": start.isoformat(), "date_to": end.isoformat()}


def _with_query(url: str, values: dict[str, Any]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in values.items() if value is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _as_int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            key_text = str(key)
            if any(part in key_text.lower() for part in ("token", "authorization", "cookie", "secret", "password")):
                continue
            result[key_text] = _compact(item, depth=depth + 1)
        return result
    if isinstance(value, list):
        result = [_compact(item, depth=depth + 1) for item in value[:200]]
        if len(value) > 200:
            result.append("[truncated]")
        return result
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…"
    return value


server = build_server()
