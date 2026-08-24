from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse

from .calculations import inventory_forecast, replenishment_math, unit_economics
from .client import GatewayError, SellerGatewayClient
from .config import Settings

_MCP_SCOPES = [
    "analytics:read",
    "supplier:read",
    "supplier:connect",
    "cost_price:write",
]


def build_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    gateway = SellerGatewayClient(settings)
    public_url = _secure_base_url(settings.public_url)
    auth_issuer = _secure_base_url(settings.auth_issuer)
    auth_settings = (
        AuthSettings(
            issuer_url=auth_issuer,
            resource_server_url=f"{public_url}/mcp",
            required_scopes=_MCP_SCOPES,
        )
        if public_url and auth_issuer
        else None
    )
    server = FastMCP(
        name="Интеграция агента Wildberries",
        instructions=(
            "Используйте аналитику Wildberries в рамках аккаунта Seller. Не помещайте учётные данные "
            "в запросы и результаты. Для решений сначала используйте калькулятор и прозрачный прогноз пополнения."
        ),
        host=settings.host,
        port=settings.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        auth=auth_settings,
        token_verifier=_BearerPresenceVerifier() if auth_settings else None,
    )

    @server.custom_route("/healthz", methods=["GET"], name="healthz")
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "wildberries-agent-integration"})

    @server.custom_route(
        "/.well-known/oauth-protected-resource", methods=["GET"], name="oauth_metadata"
    )
    @server.custom_route(
        "/.well-known/oauth-protected-resource/mcp",
        methods=["GET"],
        name="oauth_metadata_mcp",
    )
    async def oauth_metadata(_: Request) -> JSONResponse:
        public_url = _secure_base_url(settings.public_url)
        auth_issuer = _secure_base_url(settings.auth_issuer)
        if not public_url or not auth_issuer:
            return JSONResponse(
                {"error": "oauth_metadata_not_configured"}, status_code=503
            )
        return JSONResponse(
            {
                "resource": f"{public_url}/mcp",
                "authorization_servers": [auth_issuer],
                "scopes_supported": _MCP_SCOPES,
            }
        )

    @server.tool(
        name="wb_connect_supplier",
        title="Подключить поставщика Wildberries",
        description=(
            "Откройте существующий браузерный сценарий Seller для подключения поставщика. Пользователь вводит "
            "персональный токен Wildberries вне диалога с агентом; этот инструмент никогда не принимает и не возвращает токен."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=True,
        ),
    )
    async def wb_connect_supplier(
        supplier_id_wb: int | None = None, ctx: Context | None = None
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if auth is None and settings.requires_identity_bridge:
            return _auth_error()
        if auth is not None:
            try:
                oauth = await gateway.request(
                    authorization=auth,
                    path="/wb-oauth/authorize",
                    request_id=_request_id(ctx),
                )
                if isinstance(oauth, dict):
                    authorization_url = oauth.get("authorization_url") or oauth.get("url")
                    authorization_url = _safe_handoff_url(
                        authorization_url, require_https=True
                    )
                    if authorization_url:
                        return {
                            "ok": True,
                            "url": authorization_url,
                            "flow": "OAuth Wildberries в Seller",
                            "security": "Подтвердите доступ в браузере; учётные данные остаются вне диалога с агентом.",
                        }
            except GatewayError as error:
                # A deployment may not expose WB OAuth yet; the explicit browser handoff remains safe.
                if _is_identity_boundary_error(error):
                    return _gateway_error(error)
        if not settings.connect_url:
            return {
                "ok": False,
                "error": {"code": "connect_url_not_configured", "message": "URL подключения Seller не настроен."},
            }
        connect_url = _safe_handoff_url(
            _with_query(
                settings.connect_url,
                {
                    "source": "wildberries-agent-integration",
                    **({"supplier_id_wb": supplier_id_wb} if supplier_id_wb else {}),
                },
            ),
            require_https=settings.requires_identity_bridge,
        )
        if not connect_url:
            return {
                "ok": False,
                "error": {
                    "code": "unsafe_connect_url",
                    "message": "URL подключения Seller должен быть HTTPS без параметров, похожих на учётные данные.",
                },
            }
        return {
            "ok": True,
            "url": connect_url,
            "flow": "Интеграция Seller → Добавить поставщика → Персональный API-токен",
            "security": "Введите токен в сервисе Seller, а не в чате. Агент получает только статус подключения.",
        }

    @server.tool(
        name="wb_list_suppliers",
        title="Список подключённых поставщиков",
        description="Показывает поставщиков текущего пользователя Seller без учётных данных и значений токенов.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_list_suppliers(ctx: Context) -> dict[str, Any]:
        return await _gateway_result(gateway, settings, ctx, path="/suppliers", operation="list_suppliers")

    @server.tool(
        name="wb_analytics_summary",
        title="Сводка аналитики Wildberries",
        description="Читает продажи и заказы, а также доступные финансовые и ценовые показатели за ограниченный период.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_analytics_summary(
        supplier_id_wb: int,
        date_from: str,
        date_to: str,
        include_finance: bool = False,
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
            warnings: list[str] = []
            if include_finance:
                try:
                    finance = await gateway.request(
                        authorization=auth,
                        path="/financial_report/dashboard/v2",
                        params={"supplier_id_wb": supplier_id_wb, **period},
                        request_id=_request_id(ctx),
                    )
                    result["finance"] = _compact(finance)
                except GatewayError as error:
                    result["finance"] = {"ok": False, "error": _gateway_error(error)["error"]}
                    warnings.append("finance_unavailable_for_current_entitlement")
            if include_price_table:
                try:
                    prices = await gateway.request(
                        authorization=auth,
                        path="/price_management",
                        params={"supplier_id_wb": supplier_id_wb},
                        request_id=_request_id(ctx),
                    )
                    result["price_table"] = _compact(prices)
                except GatewayError as error:
                    result["price_table"] = {
                        "ok": False,
                        "error": _gateway_error(error)["error"],
                    }
                    warnings.append("price_table_unavailable_for_current_entitlement")
            if warnings:
                result["warnings"] = warnings
            return result
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_warehouse_stock",
        title="Остатки Wildberries по складам",
        description="Читает текущие остатки на складах Wildberries для максимум 1 000 nm_id через шлюз Seller.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_warehouse_stock(
        supplier_id_wb: int,
        nm_ids: list[int],
        chrt_ids: list[int] | None = None,
        include_fbs_stocks: bool = True,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if not 1 <= len(nm_ids) <= 1000:
            return {"ok": False, "error": {"code": "invalid_nm_ids", "message": "Укажите от 1 до 1 000 nm_id."}}
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
            if error.code == "not_found":
                return {
                    "ok": False,
                    "error": {
                        "code": "warehouse_stock_unavailable",
                        "status": error.status,
                        "message": "Настроенный шлюз Seller пока не публикует остатки по складам.",
                    },
                    "fallback": {
                        "tool": "wb_inventory_forecast",
                        "note": "Прогноз может использовать региональный дефицит и пометит распределение как эвристику.",
                    },
                }
            return _gateway_error(error)

    @server.tool(
        name="wb_unit_economics",
        title="Калькулятор юнит-экономики Wildberries",
        description="Рассчитывает цену нетто, комиссию, налог, затраты, прибыль, маржу и точку безубыточности по заданным вводным.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
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
        name="wb_upload_cost_price",
        title="Загрузить себестоимость товара",
        description=(
            "Записывает себестоимость одного товара в Seller для указанного поставщика. "
            "Перед изменением обязательно попросите пользователя подтвердить операцию и передайте confirm=true."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_upload_cost_price(
        supplier_id_wb: int,
        nm_id: int,
        cost_price: float,
        confirm: bool = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if not confirm:
            return {
                "ok": False,
                "error": {
                    "code": "confirmation_required",
                    "message": "Подтвердите запись себестоимости и повторите вызов с confirm=true.",
                },
            }
        if supplier_id_wb <= 0 or nm_id <= 0 or cost_price < 0:
            return {
                "ok": False,
                "error": {
                    "code": "invalid_cost_price_input",
                    "message": "supplier_id_wb и nm_id должны быть положительными, себестоимость — неотрицательной.",
                },
            }
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        try:
            data = await gateway.request(
                authorization=auth,
                path="/price_management/cost_price",
                method="PUT",
                params={"supplier_id_wb": supplier_id_wb},
                json={"nm_id": nm_id, "cost_price": cost_price},
                request_id=_request_id(ctx),
            )
            return {
                "ok": True,
                "supplier_id_wb": supplier_id_wb,
                "nm_id": nm_id,
                "cost_price": cost_price,
                "data": _compact(data),
            }
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_replenishment_math",
        title="Калькулятор пополнения",
        description="Рассчитывает количество пополнения по дневным продажам, остаткам, целевому покрытию и запасу безопасности.",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
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
        title="Прогноз пополнения по складам",
        description=(
            "Использует дефицит Seller и остатки по складам, чтобы оценить количество пополнения и направления. "
            "Возвращает допущения и предупреждения; это рекомендация, а не гарантия продаж."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_inventory_forecast(
        supplier_id_wb: int,
        nm_ids: list[int] | None = None,
        horizon_days: int = 30,
        safety_days: int = 7,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if nm_ids is not None and not 1 <= len(nm_ids) <= 100:
            return {"ok": False, "error": {"code": "invalid_nm_ids", "message": "Укажите от 1 до 100 nm_id или не задавайте фильтр."}}
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
                    stock_status = (
                        "warehouse_stock_unavailable"
                        if error.code == "not_found"
                        else error.code
                    )
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
    return {"ok": False, "error": {"code": "auth_required", "message": "Подключите аккаунт Seller перед запросом данных поставщика."}}


def _gateway_error(error: GatewayError) -> dict[str, Any]:
    return {"ok": False, "error": {"code": error.code, "status": error.status}}


def _is_identity_boundary_error(error: GatewayError) -> bool:
    return error.code.startswith("identity_bridge") or error.code == "gateway_https_required"


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


def _safe_handoff_url(url: Any, *, require_https: bool) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
        username = parts.username
        password = parts.password
        query_keys = [key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)]
    except ValueError:
        return None
    if parts.scheme not in ({"https"} if require_https else {"http", "https"}):
        return None
    if not parts.netloc or username or password or parts.fragment:
        return None
    if any(
        marker in key
        for key in query_keys
        for marker in ("token", "secret", "password", "authorization", "cookie", "api_key", "apikey")
    ):
        return None
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _secure_base_url(url: Any) -> str | None:
    safe = _safe_handoff_url(url, require_https=True)
    if not safe:
        return None
    parts = urlsplit(safe)
    if parts.query or parts.fragment:
        return None
    return safe.rstrip("/")


class _BearerPresenceVerifier:
    """Передаёт проверку токена identity bridge и включает стандартный вызов MCP 401."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if not isinstance(token, str) or not token.strip() or any(
            character.isspace() for character in token
        ):
            return None
        return AccessToken(
            token=token,
            client_id="seller-identity-bridge",
            scopes=_MCP_SCOPES,
        )


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
            if any(
                part in key_text.lower()
                for part in (
                    "token",
                    "authorization",
                    "cookie",
                    "secret",
                    "password",
                    "api_key",
                    "apikey",
                    "credential",
                )
            ):
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
