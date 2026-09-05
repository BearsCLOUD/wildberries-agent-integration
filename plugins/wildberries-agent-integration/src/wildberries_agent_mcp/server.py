from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.types import ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .calculations import (
    aggregate_sales_by_region,
    competitive_price_analysis,
    competitor_analysis,
    inventory_forecast,
    replenishment_math,
    seo_score,
    unit_economics,
    weather_sales_impact,
)
from .client import GatewayError, SellerGatewayClient
from .config import Settings
from .gateway_proxy import allowed_operations, build_gateway_request
from .sandbox import (
    SANDBOX_ACCESS_TOKEN,
    analytics_summary as sandbox_analytics_summary,
    connect_supplier as sandbox_connect_supplier,
    error as sandbox_error,
    inventory_inputs as sandbox_inventory_inputs,
    is_sandbox_authorization,
    proxy as sandbox_proxy,
    refresh as sandbox_refresh,
    regional_sales as sandbox_regional_sales,
    require_supplier as sandbox_require_supplier,
    result as sandbox_result,
    suppliers as sandbox_suppliers,
    upload_cost_price as sandbox_upload_cost_price,
    warehouse_stock as sandbox_warehouse_stock,
)

_MCP_SCOPES = ["wildberries-agent-free"]
_OAUTH_SECURITY_SCHEMES = [{"type": "oauth2", "scopes": _MCP_SCOPES}]


class _AgentFastMCP(FastMCP):
    """Advertise the OAuth policy on every tool for ChatGPT account linking."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            schemes = [
                {"type": scheme["type"], "scopes": list(scheme["scopes"])}
                for scheme in _OAUTH_SECURITY_SCHEMES
            ]
            tool.securitySchemes = schemes
            tool.meta = {**(tool.meta or {}), "securitySchemes": schemes}
        return tools


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
    server = _AgentFastMCP(
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
        token_verifier=(
            _SellerIdentityTokenVerifier(gateway) if auth_settings else None
        ),
    )

    @server.custom_route("/healthz", methods=["GET"], name="healthz")
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "wildberries-agent-integration"})

    @server.custom_route(
        "/.well-known/openai-apps-challenge",
        methods=["GET"],
        name="openai_apps_challenge",
    )
    async def openai_apps_challenge(_: Request) -> PlainTextResponse:
        token = settings.openai_apps_challenge.strip()
        if not token or len(token) > 512 or any(character.isspace() for character in token):
            return PlainTextResponse(
                "openai_apps_challenge_not_configured",
                status_code=404,
                headers={"Cache-Control": "no-store"},
            )
        return PlainTextResponse(
            token,
            media_type="text/plain",
            headers={"Cache-Control": "no-store"},
        )

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
                "authorization_servers": [f"{auth_issuer}/"],
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
            openWorldHint=False,
        ),
    )
    async def wb_connect_supplier(
        supplier_id_wb: int | None = None, ctx: Context | None = None
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if is_sandbox_authorization(auth):
            return sandbox_connect_supplier()
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
            "flow": (
                "Регистрация пользователя Seller → Интеграция → Добавить поставщика"
                if _is_registration_url(connect_url)
                else "Интеграция Seller → Добавить поставщика → Персональный API-токен"
            ),
            "security": "Завершите регистрацию или вход и введите токен в Seller, а не в чате. Агент получает только статус подключения.",
            "agent_next_step": "После завершения браузерного сценария повторите запрос статуса в агенте.",
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
        auth = _auth_header(ctx, settings)
        if is_sandbox_authorization(auth):
            return sandbox_suppliers()
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
        auth = _auth_header(ctx, settings)
        try:
            period = _validate_period(date_from, date_to)
        except ValueError as error:
            return _input_error_for_auth(auth, "invalid_period", str(error))
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            return sandbox_analytics_summary(
                supplier_id_wb=supplier_id_wb,
                period=period,
                include_finance=include_finance,
                include_price_table=include_price_table,
            )
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
        name="wb_competitor_analysis",
        title="Анализ конкурентов Wildberries",
        description=(
            "Находит похожие товары через существующий источник Seller и сравнивает цены. "
            "Переданные competitor_rows имеют приоритет; в песочнице доступны только переданные синтетические строки."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_competitor_analysis(
        supplier_id_wb: int,
        nm_id: int,
        competitor_rows: list[dict[str, Any]] | None = None,
        seller_price: float | None = None,
        target_position: str = "median",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if not _valid_positive_id(supplier_id_wb) or not _valid_positive_id(nm_id):
            return _input_error(
                "invalid_competitor_input",
                "supplier_id_wb и nm_id должны быть положительными целыми числами.",
            )
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        sandbox_mode = is_sandbox_authorization(auth)
        if sandbox_mode:
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
        rows = competitor_rows or []
        source = "provided_rows"
        if not rows and not sandbox_mode:
            try:
                rows = await gateway.request(
                    authorization=auth,
                    path="/open_methods/competitors",
                    params={"nm_id": nm_id},
                    request_id=_request_id(ctx),
                )
            except GatewayError as error:
                return _gateway_error(error)
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                return _gateway_error(GatewayError("upstream_invalid_json"))
            source = "seller_open_methods"
        if not rows:
            return _input_error_for_auth(
                auth,
                "source_required" if sandbox_mode else "competitor_data_unavailable",
                "Источник не вернул данные для сравнения; можно передать наблюдения в competitor_rows.",
            )
        if len(rows) > 500:
            return _input_error_for_auth(
                auth,
                "too_many_competitor_rows",
                "Передайте не более 500 строк конкурентов за один расчёт.",
            )
        try:
            analysis = competitor_analysis(
                competitor_rows=rows,
                seller_price=seller_price,
                target_position=target_position,
            )
            if sandbox_mode:
                return sandbox_result(
                    "competitor_analysis",
                    supplier_id_wb=supplier_id_wb,
                    nm_id=nm_id,
                    source="provided_rows",
                    data=_compact(analysis),
                )
            return {
                "ok": True,
                "supplier_id_wb": supplier_id_wb,
                "nm_id": nm_id,
                "source": source,
                "data": _compact(analysis),
            }
        except ValueError as error:
            return _input_error_for_auth(auth, "invalid_competitor_input", str(error))

    @server.tool(
        name="wb_wildberries_proxy",
        title="Разрешённый прокси Wildberries",
        description=(
            "Выполняет одну из закреплённых операций Seller Gateway от имени выбранного поставщика. "
            "Агент передаёт только имя операции и данные запроса: URL, HTTP-метод и токен недоступны модели."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_wildberries_proxy(
        supplier_id_wb: int,
        operation: str,
        payload: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            if operation not in allowed_operations():
                return sandbox_error(
                    "sandbox_operation_not_allowed",
                    "Виртуальная песочница разрешает только операции из фиксированного списка.",
                )
            try:
                build_gateway_request(
                    operation=operation,
                    supplier_id_wb=supplier_id_wb,
                    payload=payload,
                )
            except ValueError as error:
                return sandbox_error(
                    str(error), "Параметры операции не прошли безопасную проверку."
                )
            return sandbox_proxy(
                supplier_id_wb=supplier_id_wb,
                operation=operation,
                payload=payload,
            )
        if not _valid_positive_id(supplier_id_wb):
            return _input_error(
                "invalid_proxy_supplier",
                "supplier_id_wb должен быть положительным целым числом.",
            )
        if operation not in allowed_operations():
            return _input_error(
                "proxy_operation_not_allowed",
                "Операция не входит в разрешённый список Seller Gateway.",
            )
        try:
            request = build_gateway_request(
                operation=operation,
                supplier_id_wb=supplier_id_wb,
                payload=payload,
            )
        except ValueError as error:
            return _input_error(str(error), "Параметры операции не прошли безопасную проверку.")
        try:
            data = await gateway.request(
                authorization=auth,
                path=request["path"],
                method=request["method"],
                params=request["params"],
                json=request["json"],
                request_id=_request_id(ctx),
            )
            return {
                "ok": True,
                "supplier_id_wb": supplier_id_wb,
                "operation": operation,
                "data": _compact(data),
            }
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_refresh_analytics",
        title="Обновить аналитику Wildberries",
        description=(
            "Ставит обновление статистики выбранного поставщика в существующую очередь Seller. "
            "Период ограничен 1–366 днями; WB-токен агенту не передаётся."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def wb_refresh_analytics(
        supplier_id_wb: int,
        period: Annotated[int, Field(strict=True, ge=1, le=366)] = 1,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if not _valid_positive_id(supplier_id_wb):
            return _input_error_for_auth(
                auth,
                "invalid_refresh_supplier",
                "supplier_id_wb должен быть положительным целым числом.",
            )
        if (
            not isinstance(period, int)
            or isinstance(period, bool)
            or not 1 <= period <= 366
        ):
            return _input_error_for_auth(
                auth,
                "invalid_refresh_period",
                "period должен быть целым числом от 1 до 366.",
            )
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            return sandbox_refresh(supplier_id_wb=supplier_id_wb, period=period)
        try:
            data = await gateway.request(
                authorization=auth,
                path=f"/statistics/update/{supplier_id_wb}",
                method="POST",
                params={"period": period},
                request_id=_request_id(ctx),
            )
            return {
                "ok": True,
                "operation": "analytics_refresh",
                "supplier_id_wb": supplier_id_wb,
                "period": period,
                "data": _compact(data),
            }
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_competitive_price",
        title="Конкурентный ориентир цены",
        description=(
            "Рассчитывает ценовой коридор по переданной выборке конкурентов и необязательный нижний ориентир по себестоимости и целевой марже. "
            "Это расчёт без записи цены; комиссии, логистика и прочие расходы в нижний ориентир не входят."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_competitive_price(
        seller_price: float,
        competitor_prices: list[float],
        cost_price: float | None = None,
        target_margin_percent: float | None = None,
        target_position: str = "median",
    ) -> dict[str, Any]:
        if len(competitor_prices) > 500:
            return _input_error(
                "too_many_competitor_prices",
                "Передайте не более 500 цен конкурентов за один расчёт.",
            )
        try:
            return {
                "ok": True,
                "data": _compact(
                    competitive_price_analysis(
                        seller_price=seller_price,
                        competitor_prices=competitor_prices,
                        cost_price=cost_price,
                        target_margin_percent=target_margin_percent,
                        target_position=target_position,
                    )
                ),
            }
        except ValueError as error:
            return _input_error("invalid_competitive_price_input", str(error))

    @server.tool(
        name="wb_sales_by_region",
        title="Продажи Wildberries по регионам",
        description=(
            "Группирует продажи текущего поставщика по регионам за ограниченный период. "
            "Использует явно переданные строки либо для указанного nm_id только ленту Seller /statistics/tape/v2; не выполняет произвольные запросы."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_sales_by_region(
        supplier_id_wb: int,
        date_from: str,
        date_to: str,
        nm_id: int | None = None,
        rows: list[dict[str, Any]] | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if not _valid_positive_id(supplier_id_wb) or (
            nm_id is not None and not _valid_positive_id(nm_id)
        ):
            return _input_error_for_auth(
                auth,
                "invalid_regional_sales_input",
                "supplier_id_wb и необязательный nm_id должны быть положительными целыми числами.",
            )
        try:
            period = _validate_period(date_from, date_to)
        except ValueError as error:
            return _input_error_for_auth(auth, "invalid_period", str(error))
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            synthetic_rows = sandbox_regional_sales(
                supplier_id_wb=supplier_id_wb,
                period=period,
                nm_id=nm_id,
            )
            return sandbox_result(
                "sales_by_region",
                supplier_id_wb=supplier_id_wb,
                period=period,
                nm_id=nm_id,
                source="virtual_fixture",
                coverage="complete",
                data=_compact(aggregate_sales_by_region(rows=synthetic_rows)),
            )
        source = "provided_rows"
        coverage = "provided_rows"
        selected_rows = rows
        if selected_rows is None:
            if nm_id is None:
                return {
                    "ok": False,
                    "error": {
                        "code": "source_required",
                        "message": "Передайте региональные строки в rows или укажите nm_id для чтения ограниченной ленты Seller.",
                    },
                }
            source = "seller_statistics_tape_v2"
            try:
                payload = await gateway.request(
                    authorization=auth,
                    path="/statistics/tape/v2",
                    params={
                        "supplier_id_wb": supplier_id_wb,
                        "nm_id": nm_id,
                        "limit": 1000,
                        "page": 0,
                    },
                    request_id=_request_id(ctx),
                )
            except GatewayError as error:
                return _gateway_error(error)
            raw_rows = _payload_rows(payload)
            coverage = "truncated" if len(raw_rows) >= 1000 else "complete"
            selected_rows = _tape_sales_rows(raw_rows, period=period)
        if len(selected_rows) > 5000:
            return _input_error(
                "too_many_sales_rows",
                "Передайте не более 5 000 строк продаж за один расчёт.",
            )
        if nm_id is not None:
            selected_rows = [
                row
                for row in selected_rows
                if _as_int_value(row.get("nm_id", row.get("nmId"))) == nm_id
            ]
        selected_rows = _filter_sales_period(selected_rows, period=period)
        result = aggregate_sales_by_region(rows=selected_rows)
        return {
            "ok": True,
            "supplier_id_wb": supplier_id_wb,
            "period": period,
            "nm_id": nm_id,
            "source": source,
            "coverage": coverage,
            "data": _compact(result),
        }

    @server.tool(
        name="wb_sales_weather_impact",
        title="Связь погоды и продаж",
        description=(
            "Сопоставляет погодные наблюдения с переданными продажами или дневным числом записей Sales из Seller по supplier_id_wb, nm_id и периоду. "
            "Оценивает корреляцию температуры с продажами по совпавшим датам и регионам. "
            "Корреляция не доказывает влияние погоды или причинно-следственную связь."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_sales_weather_impact(
        weather_rows: list[dict[str, Any]],
        sales_rows: list[dict[str, Any]] | None = None,
        region: str | None = None,
        supplier_id_wb: int | None = None,
        nm_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        source = "provided_rows"
        coverage = "provided_rows"
        if sales_rows is None:
            auth = _auth_header(ctx, settings)
            if not _valid_positive_id(supplier_id_wb) or not _valid_positive_id(nm_id):
                return _input_error("source_required", "Передайте sales_rows или supplier_id_wb и nm_id.")
            if not date_from or not date_to:
                return _input_error("invalid_period", "Для чтения Seller укажите date_from и date_to.")
            try:
                period = _validate_period(date_from, date_to)
            except ValueError as error:
                return _input_error("invalid_period", str(error))
            if auth is None:
                return _auth_error()
            if is_sandbox_authorization(auth):
                return sandbox_error("source_required", "В песочнице передайте синтетические sales_rows.")
            try:
                payload = await gateway.request(
                    authorization=auth,
                    path="/statistics/sales/by-region/daily",
                    params={"supplier_id_wb": supplier_id_wb, "nm_id": nm_id, **period},
                    request_id=_request_id(ctx),
                )
            except GatewayError as error:
                return _gateway_error(error)
            if not isinstance(payload, list) or any(
                not isinstance(row, dict) or "sales_records" not in row
                for row in payload
            ):
                return _input_error("invalid_regional_daily_response", "Seller вернул несовместимый дневной ряд.")
            source = "seller_regional_daily_records"
            coverage = "stored_records_in_period"
            sales_rows = [
                {**row, "sales": row["sales_records"]} for row in payload
                if _as_int_value(row.get("nm_id")) == nm_id
            ]
        if len(sales_rows) > 5000 or len(weather_rows) > 5000:
            return _input_error(
                "too_many_weather_rows",
                "Передайте не более 5 000 строк продаж и 5 000 строк погоды за один расчёт.",
            )
        observations = _join_sales_weather(
            sales_rows=sales_rows,
            weather_rows=weather_rows,
            region=region,
        )
        result = weather_sales_impact(observations=observations)
        return {
            "ok": True,
            "region": region,
            "matched_observations": len(observations),
            "source": source,
            "coverage": coverage,
            "metric": "sales_records" if source == "seller_regional_daily_records" else "provided_sales",
            "sampling_caveat": "Расчёт использует только совпавшие даты; отсутствующие дни не считаются нулевыми продажами.",
            "seller_source_caveat": (
                "Число записей Sales включает возвраты и сторно и не равно чистым продажам. "
                "Регион взят из записи Sales; полнота загрузки WB отдельно не проверяется."
                if source == "seller_regional_daily_records" else None
            ),
            "data": _compact(result),
        }

    @server.tool(
        name="wb_seo_analytics",
        title="SEO-анализ карточки Wildberries",
        description=(
            "Оценивает полноту заголовка, описания, ключевых слов и характеристик по прозрачной эвристике. "
            "Не обещает позицию в поиске Wildberries и не обращается к алгоритмам маркетплейса."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_seo_analytics(
        title: str,
        description: str,
        keywords: list[str],
        competitor_titles: list[str] | None = None,
        characteristics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if len(title) > 1000 or len(description) > 20_000 or len(keywords) > 200:
            return _input_error(
                "seo_input_too_large",
                "Сократите заголовок, описание или список ключевых слов до поддерживаемого размера.",
            )
        if competitor_titles is not None and len(competitor_titles) > 200:
            return _input_error(
                "too_many_competitor_titles",
                "Передайте не более 200 заголовков конкурентов.",
            )
        result = seo_score(
            title=title,
            description=description,
            keywords=keywords,
            characteristics=characteristics,
        )
        result["competitor_benchmark"] = _competitor_title_benchmark(
            title=title,
            competitor_titles=competitor_titles or [],
        )
        return {"ok": True, "data": _compact(result)}

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
        auth = _auth_header(ctx, settings)
        if not 1 <= len(nm_ids) <= 1000:
            return _input_error_for_auth(
                auth, "invalid_nm_ids", "Укажите от 1 до 1 000 nm_id."
            )
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            return sandbox_warehouse_stock(
                supplier_id_wb=supplier_id_wb,
                nm_ids=nm_ids,
                include_fbs_stocks=include_fbs_stocks,
            )
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
            "Выполняется сразу по явным supplier_id_wb, nm_id и cost_price; отдельный confirm-вызов не нужен."
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
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        normalized_cost_price = _as_float_value(cost_price)
        if (
            isinstance(supplier_id_wb, bool)
            or isinstance(nm_id, bool)
            or isinstance(cost_price, bool)
            or supplier_id_wb <= 0
            or nm_id <= 0
            or normalized_cost_price is None
            or normalized_cost_price < 0
        ):
            return _input_error_for_auth(
                auth,
                "invalid_cost_price_input",
                "supplier_id_wb и nm_id должны быть положительными, себестоимость — неотрицательной.",
            )
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            return sandbox_upload_cost_price(
                supplier_id_wb=supplier_id_wb,
                nm_id=nm_id,
                cost_price=normalized_cost_price,
            )
        try:
            data = await gateway.request(
                authorization=auth,
                path="/price_management/cost_price",
                method="PUT",
                params={"supplier_id_wb": supplier_id_wb},
                json={"nm_id": nm_id, "cost_price": normalized_cost_price},
                request_id=_request_id(ctx),
            )
            if not isinstance(data, dict):
                return _unknown_write_status()
            response_nm_id = _as_int_value(data.get("nm_id"))
            response_cost_price = _as_float_value(data.get("cost_price"))
            if response_nm_id != nm_id or response_cost_price is None:
                return _unknown_write_status()
            if abs(response_cost_price - normalized_cost_price) > 0.005:
                return _unknown_write_status()
            return {
                "ok": True,
                "operation": "set_cost_price",
                "status": "updated",
                "supplier_id_wb": supplier_id_wb,
                "nm_id": nm_id,
                "cost_price": normalized_cost_price,
            }
        except GatewayError as error:
            result = _gateway_error(error)
            if error.status is None or error.status >= 500:
                result["possibly_applied"] = True
            return result

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
        auth = _auth_header(ctx, settings)
        if nm_ids is not None and not 1 <= len(nm_ids) <= 100:
            return _input_error_for_auth(
                auth,
                "invalid_nm_ids",
                "Укажите от 1 до 100 nm_id или не задавайте фильтр.",
            )
        if auth is None:
            return _auth_error()
        if is_sandbox_authorization(auth):
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            deficit_rows, stock_rows = sandbox_inventory_inputs()
            if nm_ids is not None:
                allowed = set(nm_ids)
                deficit_rows = [
                    row for row in deficit_rows if _as_int_value(row.get("nm_id")) in allowed
                ]
                stock_rows = [
                    row for row in stock_rows if _as_int_value(row.get("nmId")) in allowed
                ]
            forecast = inventory_forecast(
                deficit_rows=deficit_rows,
                stock_rows=stock_rows,
                horizon_days=horizon_days,
                safety_days=safety_days,
            )
            return sandbox_result(
                "inventory_forecast",
                supplier_id_wb=supplier_id_wb,
                warehouse_stock_status="synthetic",
                data=_compact(forecast),
            )
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
            size_status = "not_requested"
            if stock_rows and any(row.get("size") for row in deficit_rows if isinstance(row, dict)):
                try:
                    cards = await gateway.request(
                        authorization=auth, path="/open_methods/get_cards_new_detail",
                        method="POST", json={"nm_ids": list(dict.fromkeys(selected_ids))},
                        request_id=_request_id(ctx),
                    )
                    stock_rows = _stock_sizes_from_cards(stock_rows, cards)
                    size_status = "source_checked"
                except GatewayError:
                    size_status = "size_mapping_unavailable"
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
                "warehouse_size_status": size_status,
                "data": _compact(forecast),
            }
        except GatewayError as error:
            return _gateway_error(error)
        except ValueError as error:
            return {"ok": False, "error": {"code": "invalid_forecast_input", "message": str(error)}}

    return server


def _stock_sizes_from_cards(rows: list[dict[str, Any]], cards: Any) -> list[dict[str, Any]]:
    sizes: dict[tuple[int, int], str] = {}
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, dict):
            continue
        nm_id = _as_int_value(card.get("nm_id"))
        table = card.get("sizes_table")
        values = table.get("values", []) if isinstance(table, dict) else []
        for value in values if isinstance(values, list) else []:
            if not isinstance(value, dict):
                continue
            chrt_id = _as_int_value(value.get("chrt_id"))
            size = value.get("tech_size")
            if nm_id and chrt_id and isinstance(size, str) and size.strip():
                sizes[(nm_id, chrt_id)] = size.strip()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (_as_int_value(row.get("nmId")), _as_int_value(row.get("chrtId")))
        result.append({**row, "size": sizes[key]} if key in sizes else row)
    return result


def _valid_positive_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _input_error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


def _input_error_for_auth(
    authorization: str | None, code: str, message: str
) -> dict[str, Any]:
    if is_sandbox_authorization(authorization):
        return sandbox_error(code, message)
    return _input_error(code, message)


def _payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "items", "rows", "result"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _tape_sales_rows(
    rows: list[dict[str, Any]], *, period: dict[str, str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _filter_sales_period(rows, period=period):
        sale_date = _row_text(row, "sale_date", "saleDate")
        if not sale_date:
            continue
        order_type = (_row_text(row, "order_type", "orderType") or "").casefold()
        if row.get("date_return") or "возврат" in order_type or "return" in order_type:
            continue
        result.append(
            {
                "nm_id": row.get("nm_id", row.get("nmId")),
                "region_name": _row_text(row, "region_name", "regionName"),
                "date": sale_date[:10],
                "sales": 1,
                "revenue": _row_number(
                    row,
                    "sale_finished_price",
                    "saleFinishedPrice",
                    "finished_price",
                    "finishedPrice",
                )
                or 0.0,
            }
        )
    return result


def _filter_sales_period(
    rows: list[dict[str, Any]], *, period: dict[str, str]
) -> list[dict[str, Any]]:
    start = period["date_from"]
    end = period["date_to"]
    result: list[dict[str, Any]] = []
    for row in rows:
        observed_date = _row_text(
            row,
            "sale_date",
            "saleDate",
            "date",
            "day",
            "order_date",
            "orderDate",
        )
        if observed_date and not start <= observed_date[:10] <= end:
            continue
        result.append(row)
    return result


def _join_sales_weather(
    *,
    sales_rows: list[dict[str, Any]],
    weather_rows: list[dict[str, Any]],
    region: str | None,
) -> list[dict[str, Any]]:
    requested_region = region.casefold().strip() if isinstance(region, str) else ""
    weather_by_key: dict[tuple[str, str], list[float]] = {}
    weather_by_date: dict[str, list[float]] = {}
    for row in weather_rows:
        row_region = _row_text(
            row, "region", "region_name", "regionName", "oblast", "oblastOkrugName"
        )
        normalized_region = row_region.casefold() if row_region else ""
        if requested_region and normalized_region and normalized_region != requested_region:
            continue
        observed_date = _row_text(
            row, "date", "day", "weather_date", "weatherDate", "observed_at"
        )
        temperature = _row_number(row, "temperature_c", "temperature", "temp_c")
        if temperature is None:
            minimum = _row_number(row, "temperature_min_c", "temperatureMinC", "temp_min_c")
            maximum = _row_number(row, "temperature_max_c", "temperatureMaxC", "temp_max_c")
            if minimum is not None and maximum is not None:
                temperature = (minimum + maximum) / 2
        if not observed_date or temperature is None:
            continue
        day = observed_date[:10]
        weather_by_key.setdefault((day, normalized_region), []).append(temperature)
        weather_by_date.setdefault(day, []).append(temperature)

    sales_by_key: dict[tuple[str, str], float] = {}
    for row in sales_rows:
        row_region = _row_text(
            row, "region", "region_name", "regionName", "oblast", "oblastOkrugName"
        )
        normalized_region = row_region.casefold() if row_region else ""
        if requested_region and normalized_region and normalized_region != requested_region:
            continue
        observed_date = _row_text(
            row,
            "date",
            "day",
            "sale_date",
            "saleDate",
            "date_sale",
            "order_date",
            "orderDate",
        )
        sales = _row_number(
            row,
            "sales",
            "sales_count",
            "amount_sales",
            "orders",
            "amount_orders",
            "quantity",
            "revenue",
        )
        if not observed_date or sales is None:
            continue
        key = (observed_date[:10], normalized_region)
        sales_by_key[key] = sales_by_key.get(key, 0.0) + sales

    observations: list[dict[str, Any]] = []
    weather_regions = {key[1] for key in weather_by_key if key[1]}
    for (day, normalized_region), sales in sorted(sales_by_key.items()):
        temperatures = weather_by_key.get((day, normalized_region))
        # A date-only fallback is safe for an explicitly selected region, or when
        # the supplied weather has at most one named region. Never mix several
        # regional weather series into a sale row with a known region.
        if not temperatures and (
            requested_region or (not normalized_region and len(weather_regions) <= 1)
        ):
            temperatures = weather_by_date.get(day)
        if not temperatures:
            continue
        observations.append(
            {
                "date": day,
                "region": normalized_region or requested_region or None,
                "sales": sales,
                "temperature_c": sum(temperatures) / len(temperatures),
            }
        )
    return observations


def _competitor_title_benchmark(
    *, title: str, competitor_titles: list[str]
) -> dict[str, Any]:
    lengths = [len(" ".join(value.split())) for value in competitor_titles if value.strip()]
    if not lengths:
        return {
            "competitor_count": 0,
            "average_title_length": None,
            "current_title_length": len(" ".join(title.split())),
        }
    return {
        "competitor_count": len(lengths),
        "average_title_length": round(sum(lengths) / len(lengths), 1),
        "minimum_title_length": min(lengths),
        "maximum_title_length": max(lengths),
        "current_title_length": len(" ".join(title.split())),
        "note": "Сравнение отражает только длину явно переданных заголовков, а не их поисковую эффективность.",
    }


def _row_text(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _row_number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key not in row:
            continue
        value = _as_float_value(row[key])
        if value is not None:
            return value
    return None


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
    if settings.static_access_token and (
        settings.allows_static_token or settings.static_access_token == SANDBOX_ACCESS_TOKEN
    ):
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


def _unknown_write_status() -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": "write_status_unknown",
            "message": "Seller не подтвердил результат записи себестоимости.",
        },
        "possibly_applied": True,
    }


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


def _is_registration_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc.lower() == "seller.bears.ru" and parts.path.rstrip("/") == "/authentication/registration"


def _secure_base_url(url: Any) -> str | None:
    safe = _safe_handoff_url(url, require_https=True)
    if not safe:
        return None
    parts = urlsplit(safe)
    if parts.query or parts.fragment:
        return None
    return safe.rstrip("/")


class _SellerIdentityTokenVerifier:
    """Проверяет MCP bearer через Seller identity bridge до выдачи tool surface."""

    def __init__(self, gateway: SellerGatewayClient) -> None:
        self.gateway = gateway

    async def verify_token(self, token: str) -> AccessToken | None:
        if not isinstance(token, str) or not token.strip() or any(
            character.isspace() for character in token
        ):
            return None
        if token == SANDBOX_ACCESS_TOKEN:
            return AccessToken(
                token=token,
                client_id="reviewer-sandbox",
                scopes=_MCP_SCOPES,
            )
        try:
            await self.gateway.verify_agent_token(f"Bearer {token}")
        except GatewayError:
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


def _as_float_value(value: Any) -> float | None:
    try:
        result = float(value) if value is not None else None
        return result if result is not None and isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _compact(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
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
