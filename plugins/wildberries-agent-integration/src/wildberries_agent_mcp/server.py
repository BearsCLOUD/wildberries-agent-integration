from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
)

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
from .public_pages import landing, privacy, support, terms
from .sandbox import (
    SANDBOX_ACCESS_TOKEN,
    analytics_summary as sandbox_analytics_summary,
    connect_telegram as sandbox_connect_telegram,
    connect_supplier as sandbox_connect_supplier,
    connection_status as sandbox_connection_status,
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
    weather_inputs as sandbox_weather_inputs,
    warehouse_stock as sandbox_warehouse_stock,
)

_MCP_SCOPES = ["wildberries-agent-free"]
_NOAUTH_TOOLS = frozenset(
    {
        "wb_competitive_price",
        "wb_replenishment_math",
        "wb_seo_analytics",
        "wb_unit_economics",
    }
)
_OAUTH_SECURITY_SCHEMES = [{"type": "oauth2", "scopes": _MCP_SCOPES}]
_NOAUTH_SECURITY_SCHEMES = [{"type": "noauth"}]
_REVIEWER_DEMO = Path(__file__).with_name("assets") / "reviewer-demo.mp4"
_TOOL_INVOCATION_LABELS = {
    "wb_connect_supplier": (
        "Открываю подключение Wildberries",
        "Подключение Wildberries открыто",
    ),
    "wb_connection_status": (
        "Проверяю подключение Wildberries",
        "Подключение Wildberries проверено",
    ),
    "wb_connect_telegram": (
        "Открываю подключение Telegram",
        "Подключение Telegram открыто",
    ),
    "wb_list_suppliers": (
        "Получаю кабинеты Wildberries",
        "Кабинеты Wildberries получены",
    ),
    "wb_analytics_summary": (
        "Считаю аналитику Wildberries",
        "Аналитика Wildberries готова",
    ),
    "wb_competitor_analysis": (
        "Сравниваю товары конкурентов",
        "Сравнение конкурентов готово",
    ),
    "wb_wildberries_proxy": (
        "Получаю данные Wildberries",
        "Данные Wildberries получены",
    ),
    "wb_refresh_analytics": (
        "Запускаю обновление аналитики",
        "Обновление аналитики запущено",
    ),
    "wb_competitive_price": (
        "Рассчитываю ценовой коридор",
        "Ценовой коридор рассчитан",
    ),
    "wb_sales_by_region": (
        "Считаю продажи по регионам",
        "Продажи по регионам рассчитаны",
    ),
    "wb_sales_weather_impact": (
        "Сопоставляю погоду и продажи",
        "Связь погоды и продаж рассчитана",
    ),
    "wb_seo_analytics": ("Проверяю SEO карточки", "SEO карточки проверено"),
    "wb_warehouse_stock": ("Получаю остатки по складам", "Остатки по складам получены"),
    "wb_unit_economics": ("Считаю юнит-экономику", "Юнит-экономика рассчитана"),
    "wb_upload_cost_price": (
        "Проверяю запись себестоимости",
        "Запись себестоимости обработана",
    ),
    "wb_replenishment_math": (
        "Считаю количество пополнения",
        "Количество пополнения рассчитано",
    ),
    "wb_inventory_forecast": ("Строю прогноз пополнения", "Прогноз пополнения готов"),
}


class _AgentFastMCP(FastMCP):
    """Advertise and enforce the per-tool authentication policy."""

    def configure_agent_guard(
        self, *, gateway: SellerGatewayClient, settings: Settings
    ) -> None:
        self._agent_gateway = gateway
        self._agent_settings = settings

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        if name not in _NOAUTH_TOOLS:
            settings = self._agent_settings
            auth = _auth_header(self.get_context(), settings)
            if auth is None:
                return _oauth_challenge(settings, code="auth_required")
            trusted_static = (
                settings.allows_static_token
                and settings.static_access_token
                and auth
                == (
                    settings.static_access_token
                    if settings.static_access_token.startswith("Bearer ")
                    else f"Bearer {settings.static_access_token}"
                )
            )
            if not is_sandbox_authorization(auth) and not trusted_static:
                try:
                    await self._agent_gateway.verify_agent_token(auth)
                except GatewayError as error:
                    if error.status == 401:
                        return _oauth_challenge(settings, code="invalid_token")
                    return CallToolResult(
                        content=[
                            TextContent(
                                type="text",
                                text="Не удалось проверить подключение Seller.",
                            )
                        ],
                        structuredContent={
                            "ok": False,
                            "error": {"code": "authentication_unavailable"},
                        },
                        isError=True,
                    )
        result = await super().call_tool(name, arguments)
        if isinstance(result, tuple) and len(result) == 2:
            content, data = result
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict) and (
                error.get("status") == 401 or error.get("code") == "auth_required"
            ):
                challenged = _oauth_challenge(
                    self._agent_settings, code="invalid_token"
                )
                challenged.content = content
                challenged.structuredContent = data
                return challenged
        return result

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            source = (
                _NOAUTH_SECURITY_SCHEMES
                if tool.name in _NOAUTH_TOOLS
                else _OAUTH_SECURITY_SCHEMES
            )
            schemes = [
                dict(
                    scheme,
                    **(
                        {"scopes": list(scheme["scopes"])} if "scopes" in scheme else {}
                    ),
                )
                for scheme in source
            ]
            tool.securitySchemes = schemes
            invoking, invoked = _TOOL_INVOCATION_LABELS[tool.name]
            tool.meta = {
                **(tool.meta or {}),
                "securitySchemes": schemes,
                "openai/toolInvocation/invoking": invoking,
                "openai/toolInvocation/invoked": invoked,
            }
        return tools


def build_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    gateway = SellerGatewayClient(settings)
    server = _AgentFastMCP(
        name="Интеграция агента Wildberries",
        instructions=(
            "Используйте специализированный инструмент приложения для каждого поддерживаемого запроса по Wildberries, "
            "даже если ответ можно приблизительно посчитать или сформулировать без инструмента. "
            "Не используйте веб-поиск вместо закрытых данных Seller: при недоступности источника честно сообщите об этом. "
            "Исключение — публичная погода, которую можно получить из открытого источника и передать в погодный анализ. "
            "Если supplier_id_wb не указан пользователем, сначала получите доступные кабинеты через wb_list_suppliers; "
            "не просите внутренний идентификатор, когда кабинет один. Не помещайте учётные данные в аргументы и результаты. "
            "Календарные периоды считайте в часовом поясе пользователя: сегодня включает текущий день; последние N дней — "
            "N завершённых календарных дней без текущего дня; если период не указан, используйте 14 завершённых дней. "
            "Всегда сообщайте точные date_from и date_to. Для расчётов вызывайте детерминированные калькуляторы, "
            "а для записи себестоимости сначала получите confirmation_required с confirm=false и выполняйте второй вызов "
            "с confirm=true только после отдельного явного подтверждения пользователя."
        ),
        host=settings.host,
        port=settings.port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        # Authentication is intentionally enforced by private tools, not by a
        # transport-wide middleware: the two pure calculators are public.
        # OAuth metadata remains advertised by the explicit well-known route.
        auth=None,
        token_verifier=None,
    )
    server.configure_agent_guard(gateway=gateway, settings=settings)

    @server.custom_route("/healthz", methods=["GET"], name="healthz")
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse(
            {"status": "ok", "service": "wildberries-agent-integration"}
        )

    @server.custom_route("/", methods=["GET"], name="landing")
    async def landing_route(_: Request) -> HTMLResponse:
        return HTMLResponse(landing())

    @server.custom_route("/privacy", methods=["GET"], name="privacy")
    async def privacy_route(_: Request) -> HTMLResponse:
        return HTMLResponse(privacy())

    @server.custom_route("/terms", methods=["GET"], name="terms")
    async def terms_route(_: Request) -> HTMLResponse:
        return HTMLResponse(terms())

    @server.custom_route("/support", methods=["GET"], name="support")
    async def support_route(_: Request) -> HTMLResponse:
        return HTMLResponse(support())

    @server.custom_route("/reviewer-demo.mp4", methods=["GET"], name="reviewer_demo")
    async def reviewer_demo(_: Request) -> FileResponse:
        return FileResponse(
            _REVIEWER_DEMO,
            media_type="video/mp4",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @server.custom_route(
        "/.well-known/openai-apps-challenge",
        methods=["GET"],
        name="openai_apps_challenge",
    )
    async def openai_apps_challenge(_: Request) -> PlainTextResponse:
        token = settings.openai_apps_challenge.strip()
        if (
            not token
            or len(token) > 512
            or any(character.isspace() for character in token)
        ):
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
            "Вызывайте, когда пользователь хочет подключить, добавить или переподключить кабинет Wildberries. "
            "Инструмент создаёт безопасный браузерный переход Seller, но сам не завершает подключение. Пользователь вводит "
            "персональный токен Wildberries только на странице Seller; инструмент никогда не принимает и не возвращает токен. "
            "Не вызывайте для простой проверки уже существующего подключения — используйте wb_connection_status."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_connect_supplier(
        supplier_id_wb: Annotated[
            int | None,
            Field(
                description=(
                    "Необязательный внутренний идентификатор существующего кабинета Seller для переподключения; "
                    "не просите его у пользователя при новом подключении."
                )
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if is_sandbox_authorization(auth):
            return sandbox_connect_supplier(supplier_id_wb=supplier_id_wb)
        if auth is None:
            return _auth_error()
        if supplier_id_wb is not None and not _valid_positive_id(supplier_id_wb):
            return _input_error_for_auth(
                auth,
                "invalid_supplier_id",
                "supplier_id_wb должен быть положительным целым числом.",
            )
        try:
            data = await gateway.request(
                authorization=auth,
                path="/agent/connection/supplier",
                method="POST",
                json=(
                    {"supplier_id_wb": supplier_id_wb}
                    if supplier_id_wb is not None
                    else {}
                ),
                request_id=_request_id(ctx),
            )
            return _connection_result(data, default_status="pending")
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_connection_status",
        title="Статус подключения Wildberries",
        description=(
            "Вызывайте, когда пользователь спрашивает, подключён ли кабинет Wildberries, или когда данные Seller недоступны. "
            "Возвращает состояние подключения текущего аккаунта без учётных данных. Не утверждайте, что требуется "
            "переподключение, пока этот инструмент не вернул соответствующий статус."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_connection_status(ctx: Context | None = None) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if is_sandbox_authorization(auth):
            return sandbox_connection_status()
        if auth is None:
            return _auth_error()
        try:
            data = await gateway.request(
                authorization=auth,
                path="/agent/connection/status",
                request_id=_request_id(ctx),
            )
            return _connection_result(data, default_status="unknown")
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_connect_telegram",
        title="Подключить Telegram",
        description=(
            "Вызывайте, когда пользователь хочет подключить Telegram к Seller для уведомлений. Инструмент только запускает "
            "безопасный сценарий привязки и не настраивает типы, расписание или правила уведомлений. Не обещайте, что правила "
            "уведомлений изменены, если отдельного инструмента для этого нет."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_connect_telegram(ctx: Context | None = None) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if is_sandbox_authorization(auth):
            return sandbox_connect_telegram()
        if auth is None:
            return _auth_error()
        try:
            data = await gateway.request(
                authorization=auth,
                path="/agent/connection/telegram",
                method="POST",
                json={},
                request_id=_request_id(ctx),
            )
            return _connection_result(data, default_status="pending")
        except GatewayError as error:
            return _gateway_error(error)

    @server.tool(
        name="wb_list_suppliers",
        title="Список подключённых поставщиков",
        description=(
            "Вызывайте, когда пользователь просит показать подключённые кабинеты Wildberries, а также перед инструментом "
            "с обязательным supplier_id_wb, если кабинет ещё не определён. Возвращает только доступные текущему пользователю "
            "кабинеты без учётных данных и токенов; если кабинет один, используйте его без дополнительного вопроса."
        ),
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
        return await _gateway_result(
            gateway, settings, ctx, path="/agent/suppliers", operation="list_suppliers"
        )

    @server.tool(
        name="wb_analytics_summary",
        title="Сводка аналитики Wildberries",
        description=(
            "Вызывайте для пользовательских запросов о заказах, продажах, возвратах, выручке, комиссиях, логистике или общей "
            "аналитике торговли за период. Не оценивайте эти показатели самостоятельно и не заменяйте их веб-поиском. "
            "date_from и date_to включительны; относительный период преобразуйте по общим правилам сервера и сообщите точные даты. "
            "Разницу между выручкой и расходами WB не называйте чистой прибылью без себестоимости, налогов и прочих затрат."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_analytics_summary(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        date_from: Annotated[
            str,
            Field(description="Первая включённая дата периода в формате YYYY-MM-DD."),
        ],
        date_to: Annotated[
            str,
            Field(
                description="Последняя включённая дата периода в формате YYYY-MM-DD."
            ),
        ],
        include_finance: Annotated[
            bool,
            Field(
                description="Запросить комиссии, логистику и доступные финансовые показатели."
            ),
        ] = False,
        include_price_table: Annotated[
            bool,
            Field(description="Дополнительно запросить текущую таблицу цен товаров."),
        ] = False,
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
                path="/agent/statistics/report/combined",
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
                        path="/agent/financial_report/dashboard/v2",
                        params={"supplier_id_wb": supplier_id_wb, **period},
                        request_id=_request_id(ctx),
                    )
                    result["finance"] = _compact(finance)
                except GatewayError as error:
                    result["finance"] = {
                        "ok": False,
                        "error": _gateway_error(error)["error"],
                    }
                    warnings.append("finance_unavailable_for_current_entitlement")
            if include_price_table:
                try:
                    prices = await gateway.request(
                        authorization=auth,
                        path="/agent/price_management",
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
            "Вызывайте, когда пользователь просит сравнить свой товар с похожими предложениями или понять, дороже ли он рынка. "
            "Инструмент получает похожие товары из принадлежащего Seller источника и рассчитывает прозрачное сравнение цен; "
            "переданные competitor_rows имеют приоритет. Не заменяйте недоступные закрытые данные веб-поиском и не выдумывайте цены. "
            "Для расчёта только по уже известному списку цен без поиска товаров используйте wb_competitive_price."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_competitor_analysis(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        nm_id: Annotated[
            int, Field(description="Артикул Wildberries (nm_id) товара пользователя.")
        ],
        competitor_rows: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description="Необязательные наблюдения конкурентов; каждая строка должна содержать положительную цену."
            ),
        ] = None,
        seller_price: Annotated[
            float | None,
            Field(
                description="Необязательная текущая цена товара пользователя в рублях."
            ),
        ] = None,
        target_position: Annotated[
            str, Field(description="Целевой ориентир: low, median или high.")
        ] = "median",
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
        if not rows and sandbox_mode:
            rows = [
                {"nm_id": 900000201, "sale_price": 1090.0},
                {"nm_id": 900000202, "sale_price": 1190.0},
                {"nm_id": 900000203, "sale_price": 1290.0},
                {"nm_id": 900000204, "sale_price": 1390.0},
                {"nm_id": 900000205, "sale_price": 1490.0},
            ]
            seller_price = seller_price if seller_price is not None else 1200.0
            source = "virtual_fixture"
        if not rows and not sandbox_mode:
            try:
                rows = await gateway.request(
                    authorization=auth,
                    path="/agent/open_methods/competitors",
                    params={"nm_id": nm_id},
                    request_id=_request_id(ctx),
                )
            except GatewayError as error:
                return _gateway_error(error)
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) for row in rows
            ):
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
                    source=source,
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
            "Вызывайте этот резервный инструмент для разрешённых чтений Seller/Wildberries, у которых нет специализированного инструмента, "
            "например отзывов, карточек или статуса обновления. Для аналитики, конкурентов, регионов, остатков и прогнозов "
            "используйте соответствующий специализированный wb_* инструмент, а не этот прокси. Не заменяйте ошибку закрытого "
            "источника веб-поиском. Агент передаёт только operation и payload: URL, HTTP-метод и токен модели недоступны."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_wildberries_proxy(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        operation: Annotated[
            str,
            Field(
                description=(
                    "Идентификатор одной операции из фиксированного каталога Seller Gateway; "
                    "для отзывов используйте feedbacks или feedback_average."
                )
            ),
        ],
        payload: Annotated[
            dict[str, Any] | None,
            Field(
                description="Параметры выбранной операции без URL, HTTP-метода и учётных данных."
            ),
        ] = None,
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
            return _input_error(
                str(error), "Параметры операции не прошли безопасную проверку."
            )
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
            "Вызывайте, когда пользователь просит обновить, синхронизировать или сделать свежей аналитику кабинета. "
            "Ставит фоновое обновление статистики выбранного поставщика в очередь Seller, но не ждёт завершения отчёта. "
            "period — число последних дней от 1 до 366; постановка задачи не требует подтверждения и не удаляет данные."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def wb_refresh_analytics(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        period: Annotated[
            int,
            Field(
                strict=True,
                ge=1,
                le=366,
                description="Количество последних календарных дней для обновления, от 1 до 366.",
            ),
        ] = 1,
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
                path=f"/agent/statistics/update/{supplier_id_wb}",
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
            "Всегда вызывайте для расчёта конкурентного ценового диапазона по известным ценам, даже если арифметику можно "
            "выполнить в ответе модели. Инструмент детерминированно рассчитывает межквартильный коридор, позицию цены и целевой "
            "ориентир, а при наличии себестоимости и маржи — нижнюю границу. Ничего не записывает. Комиссии, логистика и прочие "
            "расходы в границу не входят; для полной экономики используйте wb_unit_economics."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_competitive_price(
        seller_price: Annotated[
            float, Field(description="Текущая цена товара пользователя в рублях.")
        ],
        competitor_prices: Annotated[
            list[float],
            Field(
                description="От 1 до 500 известных положительных цен конкурентов в рублях."
            ),
        ],
        cost_price: Annotated[
            float | None,
            Field(description="Необязательная себестоимость единицы товара в рублях."),
        ] = None,
        target_margin_percent: Annotated[
            float | None,
            Field(description="Необязательная целевая маржа в процентах от цены."),
        ] = None,
        target_position: Annotated[
            str,
            Field(description="Целевой ориентир внутри выборки: low, median или high."),
        ] = "median",
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        if len(competitor_prices) > 500:
            return _input_error(
                "too_many_competitor_prices",
                "Передайте не более 500 цен конкурентов за один расчёт.",
            )
        try:
            data = _compact(
                competitive_price_analysis(
                    seller_price=seller_price,
                    competitor_prices=competitor_prices,
                    cost_price=cost_price,
                    target_margin_percent=target_margin_percent,
                    target_position=target_position,
                )
            )
            if is_sandbox_authorization(_auth_header(ctx, settings)):
                return sandbox_result("competitive_price", data=data)
            return {"ok": True, "data": data}
        except ValueError as error:
            return _input_error("invalid_competitive_price_input", str(error))

    @server.tool(
        name="wb_sales_by_region",
        title="Продажи Wildberries по регионам",
        description=(
            "Вызывайте, когда пользователь спрашивает, где товары продаются лучше или хуже, либо просит продажи по регионам. "
            "Группирует региональные записи Seller за включительный период date_from—date_to; относительные даты преобразуйте "
            "по общим правилам сервера и сообщите точный период. Не используйте веб-поиск. Записи Sales включают возвраты и "
            "сторно и поэтому не являются чистыми продажами."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_sales_by_region(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        date_from: Annotated[
            str,
            Field(description="Первая включённая дата периода в формате YYYY-MM-DD."),
        ],
        date_to: Annotated[
            str,
            Field(
                description="Последняя включённая дата периода в формате YYYY-MM-DD."
            ),
        ],
        nm_id: Annotated[
            int | None,
            Field(
                description="Необязательный артикул Wildberries для фильтрации отчёта."
            ),
        ] = None,
        rows: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description="Необязательные подготовленные региональные строки; обычно оставьте пустым для чтения Seller."
            ),
        ] = None,
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
                        "message": "Передайте региональные строки в rows или укажите nm_id для чтения дневного отчёта Seller.",
                    },
                }
            source = "seller_regional_daily_records"
            try:
                payload = await gateway.request(
                    authorization=auth,
                    path="/agent/statistics/sales/by-region/daily",
                    params={
                        "supplier_id_wb": supplier_id_wb,
                        "nm_id": nm_id,
                        **period,
                    },
                    request_id=_request_id(ctx),
                )
            except GatewayError as error:
                return _gateway_error(error)
            if not isinstance(payload, list) or any(
                not isinstance(row, dict)
                or "sales_records" not in row
                or "sales_records_value" not in row
                for row in payload
            ):
                return _input_error(
                    "invalid_regional_daily_response",
                    "Seller вернул несовместимый дневной ряд.",
                )
            coverage = "stored_records_in_period"
            selected_rows = [
                {
                    **row,
                    "sales": row["sales_records"],
                    "revenue": row["sales_records_value"],
                }
                for row in payload
            ]
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
        if source == "seller_regional_daily_records":
            record_names = {
                "sales": "sales_records",
                "revenue": "sales_records_value",
                "sales_share_percent": "records_share_percent",
                "revenue_share_percent": "records_value_share_percent",
            }
            result["regions"] = [
                {record_names.get(key, key): value for key, value in row.items()}
                for row in result["regions"]
            ]
            result["totals"] = {
                record_names.get(key, key): value
                for key, value in result["totals"].items()
            }
            result["assumption"] = (
                "Записи Sales включают возвраты и сторно; суммы finished_price не равны чистой выручке. "
                "Регион взят из Sales. Полнота исходной загрузки WB отдельно не проверена."
            )
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
            "Вызывайте, когда пользователь просит проверить связь температуры или погоды с продажами товара. Сопоставляет "
            "публичный погодный ряд с дневными записями Sales из Seller по артикулу, региону и включительному периоду. "
            "Публичную погоду разрешено получить из открытого источника, но продажи нельзя заменять веб-поиском. "
            "Всегда сообщайте размер совпавшей выборки и не называйте корреляцию влиянием или причиной."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_sales_weather_impact(
        weather_rows: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description="Публичные погодные наблюдения с date, region и temperature_c; в reviewer sandbox можно не передавать."
            ),
        ] = None,
        sales_rows: Annotated[
            list[dict[str, Any]] | None,
            Field(
                description="Необязательный подготовленный ряд продаж; обычно оставьте пустым для чтения Seller."
            ),
        ] = None,
        region: Annotated[
            str | None,
            Field(
                description="Регион или город, одинаково обозначенный в продажах и погодном ряду."
            ),
        ] = None,
        supplier_id_wb: Annotated[
            int | None,
            Field(
                description="Идентификатор кабинета из wb_list_suppliers, обязательный при чтении Seller."
            ),
        ] = None,
        nm_id: Annotated[
            int | None,
            Field(description="Артикул Wildberries, обязательный при чтении Seller."),
        ] = None,
        date_from: Annotated[
            str | None,
            Field(
                description="Первая включённая дата периода YYYY-MM-DD при чтении Seller."
            ),
        ] = None,
        date_to: Annotated[
            str | None,
            Field(
                description="Последняя включённая дата периода YYYY-MM-DD при чтении Seller."
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        auth = _auth_header(ctx, settings)
        if auth is None:
            return _auth_error()
        source = "provided_rows"
        coverage = "provided_rows"
        sandbox_mode = is_sandbox_authorization(auth)
        period: dict[str, str] | None = None
        if date_from and date_to:
            try:
                period = _validate_period(date_from, date_to)
            except ValueError as error:
                return _input_error_for_auth(auth, "invalid_period", str(error))
        if sandbox_mode and sales_rows is None:
            if not _valid_positive_id(supplier_id_wb) or not _valid_positive_id(nm_id):
                return sandbox_error(
                    "source_required",
                    "Укажите supplier_id_wb и nm_id для виртуального погодного анализа.",
                )
            supplier_error = sandbox_require_supplier(supplier_id_wb)
            if supplier_error:
                return supplier_error
            if period is None:
                return sandbox_error(
                    "invalid_period",
                    "Укажите date_from и date_to для виртуального погодного анализа.",
                )
            sales_rows, default_weather = sandbox_weather_inputs(
                period=period,
                region=region,
                nm_id=nm_id,
            )
            if not weather_rows:
                weather_rows = default_weather
            source = "virtual_fixture"
            coverage = "complete"
        if weather_rows is None:
            return _input_error_for_auth(
                auth,
                "weather_source_required",
                "Передайте публичные погодные наблюдения в weather_rows.",
            )
        if sales_rows is None:
            if not _valid_positive_id(supplier_id_wb) or not _valid_positive_id(nm_id):
                return _input_error(
                    "source_required",
                    "Передайте sales_rows или supplier_id_wb и nm_id.",
                )
            if not date_from or not date_to:
                return _input_error(
                    "invalid_period", "Для чтения Seller укажите date_from и date_to."
                )
            if period is None:
                return _input_error(
                    "invalid_period", "Для чтения Seller укажите date_from и date_to."
                )
            try:
                payload = await gateway.request(
                    authorization=auth,
                    path="/agent/statistics/sales/by-region/daily",
                    params={
                        "supplier_id_wb": supplier_id_wb,
                        "nm_id": nm_id,
                        **period,
                        **(
                            {"region": region.strip()}
                            if region and region.strip()
                            else {}
                        ),
                    },
                    request_id=_request_id(ctx),
                )
            except GatewayError as error:
                return _gateway_error(error)
            if not isinstance(payload, list) or any(
                not isinstance(row, dict) or "sales_records" not in row
                for row in payload
            ):
                return _input_error(
                    "invalid_regional_daily_response",
                    "Seller вернул несовместимый дневной ряд.",
                )
            source = "seller_regional_daily_records"
            coverage = "stored_records_in_period"
            sales_rows = [
                {**row, "sales": row["sales_records"]}
                for row in payload
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
        response = {
            "ok": True,
            "region": region,
            "matched_observations": len(observations),
            "source": source,
            "coverage": coverage,
            "metric": "sales_records"
            if source == "seller_regional_daily_records"
            else "provided_sales",
            "sampling_caveat": "Расчёт использует только совпавшие даты; отсутствующие дни не считаются нулевыми продажами.",
            "seller_source_caveat": (
                "Число записей Sales включает возвраты и сторно и не равно чистым продажам. "
                "Регион взят из записи Sales; полнота загрузки WB отдельно не проверяется."
                if source == "seller_regional_daily_records"
                else None
            ),
            "data": _compact(result),
        }
        if sandbox_mode:
            response.pop("ok")
            return sandbox_result("sales_weather_impact", **response)
        return response

    @server.tool(
        name="wb_seo_analytics",
        title="SEO-анализ карточки Wildberries",
        description=(
            "Всегда вызывайте, когда пользователь просит проверить SEO карточки, оценить заголовок, описание или ключевые "
            "слова, даже если модель может дать общие советы сама. Возвращает детерминированный score, разбивку и приоритетные "
            "улучшения по прозрачной эвристике. Ничего не публикует и не обещает позицию в поиске Wildberries."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_seo_analytics(
        title: Annotated[str, Field(description="Текущее название карточки товара.")],
        description: Annotated[
            str, Field(description="Текущее описание карточки товара.")
        ],
        keywords: Annotated[
            list[str],
            Field(description="Целевые поисковые фразы и ключевые слова карточки."),
        ],
        competitor_titles: Annotated[
            list[str] | None,
            Field(
                description="Необязательные названия похожих карточек для сравнения длины."
            ),
        ] = None,
        characteristics: Annotated[
            dict[str, Any] | None,
            Field(description="Необязательные заполненные характеристики карточки."),
        ] = None,
        ctx: Context | None = None,
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
        if is_sandbox_authorization(_auth_header(ctx, settings)):
            return sandbox_result("seo_analytics", data=_compact(result))
        return {"ok": True, "data": _compact(result)}

    @server.tool(
        name="wb_warehouse_stock",
        title="Остатки Wildberries по складам",
        description=(
            "Вызывайте, когда пользователь спрашивает текущие остатки товара, наличие по складам или где заканчивается запас. "
            "Читает Seller/Wildberries для 1–1000 артикулов и не изменяет остатки. Не заменяйте недоступные складские данные "
            "веб-поиском; прогноз будущего пополнения выполняет wb_inventory_forecast."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_warehouse_stock(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        nm_ids: Annotated[
            list[int], Field(description="От 1 до 1000 артикулов Wildberries (nm_id).")
        ],
        chrt_ids: Annotated[
            list[int] | None,
            Field(
                description="Необязательные идентификаторы вариантов товара (chrt_id)."
            ),
        ] = None,
        include_fbs_stocks: Annotated[
            bool, Field(description="Включить остатки FBS; по умолчанию включены.")
        ] = True,
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
                path="/agent/price_management/stocks-report/wb-warehouses",
                method="POST",
                params={
                    "supplier_id_wb": supplier_id_wb,
                    "include_fbs_stocks": include_fbs_stocks,
                },
                json={
                    "nmIds": nm_ids,
                    "chrtIds": chrt_ids,
                    "limit": 250000,
                    "offset": 0,
                },
                request_id=_request_id(ctx),
            )
            return {
                "ok": True,
                "supplier_id_wb": supplier_id_wb,
                "data": _compact(data),
            }
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
        description=(
            "Всегда вызывайте для расчёта прибыли с единицы, маржи, рентабельности, точки безубыточности или целевой цены, "
            "даже если модель может выполнить арифметику сама. Детерминированно учитывает только явно переданные цену, "
            "скидку, себестоимость, комиссию, логистику, хранение, рекламу, налог и прочие затраты; отсутствующие затраты "
            "считает нулевыми и не должен выдавать неполный расчёт за фактическую чистую прибыль."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_unit_economics(
        price: Annotated[
            float, Field(description="Цена до скидки за единицу товара в рублях.")
        ],
        cost_price: Annotated[
            float, Field(description="Себестоимость единицы товара в рублях.")
        ],
        commission_percent: Annotated[
            float,
            Field(description="Комиссия Wildberries в процентах от цены после скидки."),
        ],
        logistics_per_unit: Annotated[
            float, Field(description="Логистика на единицу товара в рублях.")
        ] = 0.0,
        storage_per_unit: Annotated[
            float, Field(description="Хранение на единицу товара в рублях.")
        ] = 0.0,
        advertising_per_unit: Annotated[
            float, Field(description="Реклама на единицу товара в рублях.")
        ] = 0.0,
        tax_percent: Annotated[
            float, Field(description="Налог в процентах от цены после скидки.")
        ] = 0.0,
        other_costs_per_unit: Annotated[
            float, Field(description="Прочие затраты на единицу товара в рублях.")
        ] = 0.0,
        discount_percent: Annotated[
            float, Field(description="Скидка покупателю в процентах от исходной цены.")
        ] = 0.0,
        target_margin_percent: Annotated[
            float | None,
            Field(
                description="Необязательная целевая маржа в процентах от цены после скидки."
            ),
        ] = None,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        try:
            data = unit_economics(
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
            )
            if is_sandbox_authorization(_auth_header(ctx, settings)):
                return sandbox_result("unit_economics", data=_compact(data))
            return {"ok": True, **data}
        except ValueError as error:
            return {
                "ok": False,
                "error": {"code": "invalid_calculator_input", "message": str(error)},
            }

    @server.tool(
        name="wb_upload_cost_price",
        title="Загрузить себестоимость товара",
        description=(
            "Вызывайте, когда пользователь просит установить или изменить себестоимость товара в Seller. Это двухшаговая "
            "перезапись: первый вызов всегда делайте с confirm=false, покажите пользователю кабинет, артикул и сумму из "
            "confirmation_required, затем остановитесь. Только после отдельного явного подтверждения пользователя повторите "
            "тот же вызов с confirm=true. Не используйте ранее данное общее согласие и не меняйте значения между вызовами."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_upload_cost_price(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        nm_id: Annotated[
            int,
            Field(
                description="Артикул Wildberries (nm_id), для которого меняется себестоимость."
            ),
        ],
        cost_price: Annotated[
            float,
            Field(
                description="Новая неотрицательная себестоимость единицы товара в рублях."
            ),
        ],
        confirm: Annotated[
            bool,
            Field(
                description=(
                    "Всегда false при первом вызове. Установите true только после того, как пользователь увидел точную "
                    "сводку confirmation_required и отдельно подтвердил эту запись."
                )
            ),
        ] = False,
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
        if confirm is not True:
            response = {
                "ok": False,
                "error": {
                    "code": "confirmation_required",
                    "message": (
                        "Подтвердите перезапись себестоимости, повторив вызов с "
                        "confirm=true."
                    ),
                },
                "requested": {
                    "supplier_id_wb": supplier_id_wb,
                    "nm_id": nm_id,
                    "cost_price": normalized_cost_price,
                },
            }
            if is_sandbox_authorization(auth):
                response.update(
                    {
                        "sandbox": True,
                        "synthetic": True,
                        "identity": "reviewer-sandbox",
                        "source": "virtual_sandbox",
                        "operation": "set_cost_price_preview",
                    }
                )
            return response
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
                path="/agent/price_management/cost_price",
                method="PUT",
                params={"supplier_id_wb": supplier_id_wb},
                json={
                    "nm_id": nm_id,
                    "cost_price": normalized_cost_price,
                    "confirm": True,
                },
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
        description=(
            "Всегда вызывайте для точного расчёта количества к отправке по средним дневным продажам, текущему остатку, "
            "товару в пути, целевому покрытию и страховочному запасу, даже если модель может посчитать сама. "
            "Использует фиксированную формулу и округление вверх; не читает Seller и не распределяет товар по складам. "
            "Для рекомендаций на основе кабинета и складов используйте wb_inventory_forecast."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_replenishment_math(
        daily_sales: Annotated[
            float, Field(description="Среднее число проданных единиц в день.")
        ],
        current_stock: Annotated[
            int, Field(description="Доступный текущий остаток в единицах.")
        ],
        target_days: Annotated[
            int, Field(description="Желаемое число дней основного покрытия.")
        ],
        safety_days: Annotated[
            int, Field(description="Дополнительное число дней страхового запаса.")
        ],
        inbound_qty: Annotated[
            int, Field(description="Количество единиц, уже находящихся в поставке.")
        ] = 0,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        try:
            data = replenishment_math(
                daily_sales=daily_sales,
                current_stock=current_stock,
                target_days=target_days,
                safety_days=safety_days,
                inbound_qty=inbound_qty,
            )
            if is_sandbox_authorization(_auth_header(ctx, settings)):
                return sandbox_result("replenishment_math", data=_compact(data))
            return {"ok": True, **data}
        except ValueError as error:
            return {
                "ok": False,
                "error": {"code": "invalid_replenishment_input", "message": str(error)},
            }

    @server.tool(
        name="wb_inventory_forecast",
        title="Прогноз пополнения по складам",
        description=(
            "Вызывайте, когда пользователь просит определить, какие товары срочно пополнить, сколько отправить и на какие "
            "склады или регионы, исходя из его кабинета Seller. Читает доступный спрос и остатки, затем возвращает прозрачный "
            "прогноз с допущениями на заданный горизонт. Не заменяйте закрытые данные веб-поиском и не обещайте будущие продажи; "
            "для расчёта одного количества только по заданным числам используйте wb_replenishment_math."
        ),
        annotations=ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def wb_inventory_forecast(
        supplier_id_wb: Annotated[
            int,
            Field(
                description="Положительный идентификатор кабинета из wb_list_suppliers."
            ),
        ],
        nm_ids: Annotated[
            list[int] | None,
            Field(description="Необязательный фильтр из 1–100 артикулов Wildberries."),
        ] = None,
        horizon_days: Annotated[
            int,
            Field(description="Горизонт основного покрытия в днях; по умолчанию 30."),
        ] = 30,
        safety_days: Annotated[
            int,
            Field(description="Дополнительный страховой запас в днях; по умолчанию 7."),
        ] = 7,
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
                    row
                    for row in deficit_rows
                    if _as_int_value(row.get("nm_id")) in allowed
                ]
                stock_rows = [
                    row
                    for row in stock_rows
                    if _as_int_value(row.get("nmId")) in allowed
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
                path="/agent/statistics/orders",
                params={"supplier_id_wb": supplier_id_wb},
                request_id=_request_id(ctx),
            )
            deficit_rows = (
                deficits
                if isinstance(deficits, list)
                else deficits.get("data", [])
                if isinstance(deficits, dict)
                else []
            )
            if nm_ids is not None:
                allowed = set(nm_ids)
                deficit_rows = [
                    row
                    for row in deficit_rows
                    if isinstance(row, dict)
                    and _as_int_value(row.get("nm_id", row.get("nmId"))) in allowed
                ]
            selected_ids = [
                row.get("nm_id", row.get("nmId"))
                for row in deficit_rows
                if isinstance(row, dict)
            ]
            selected_ids = [int(value) for value in selected_ids if value is not None][
                :100
            ]
            stock_rows: list[dict[str, Any]] = []
            stock_status = "not_requested"
            if selected_ids:
                try:
                    stocks = await gateway.request(
                        authorization=auth,
                        path="/agent/price_management/stocks-report/wb-warehouses",
                        method="POST",
                        params={
                            "supplier_id_wb": supplier_id_wb,
                            "include_fbs_stocks": True,
                        },
                        json={
                            "nmIds": selected_ids,
                            "chrtIds": None,
                            "limit": 250000,
                            "offset": 0,
                        },
                        request_id=_request_id(ctx),
                    )
                    stock_rows = (
                        stocks.get("data", []) if isinstance(stocks, dict) else []
                    )
                    stock_status = "ok"
                except GatewayError as error:
                    stock_status = (
                        "warehouse_stock_unavailable"
                        if error.code == "not_found"
                        else error.code
                    )
            size_status = "not_requested"
            if stock_rows and any(
                row.get("size") for row in deficit_rows if isinstance(row, dict)
            ):
                try:
                    cards = await gateway.request(
                        authorization=auth,
                        path="/agent/open_methods/get_cards_new_detail",
                        method="POST",
                        json={"nm_ids": list(dict.fromkeys(selected_ids))},
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
            return {
                "ok": False,
                "error": {"code": "invalid_forecast_input", "message": str(error)},
            }

    return server


def _stock_sizes_from_cards(
    rows: list[dict[str, Any]], cards: Any
) -> list[dict[str, Any]]:
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
    if authorization is None:
        return _auth_error()
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
        if (
            requested_region
            and normalized_region
            and normalized_region != requested_region
        ):
            continue
        observed_date = _row_text(
            row, "date", "day", "weather_date", "weatherDate", "observed_at"
        )
        temperature = _row_number(row, "temperature_c", "temperature", "temp_c")
        if temperature is None:
            minimum = _row_number(
                row, "temperature_min_c", "temperatureMinC", "temp_min_c"
            )
            maximum = _row_number(
                row, "temperature_max_c", "temperatureMaxC", "temp_max_c"
            )
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
        if (
            requested_region
            and normalized_region
            and normalized_region != requested_region
        ):
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
    lengths = [
        len(" ".join(value.split())) for value in competitor_titles if value.strip()
    ]
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
        settings.allows_static_token
        or settings.static_access_token == SANDBOX_ACCESS_TOKEN
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
        data = await gateway.request(
            authorization=auth, path=path, request_id=_request_id(ctx)
        )
        return {"ok": True, "operation": operation, "data": _compact(data)}
    except GatewayError as error:
        return _gateway_error(error)


def _auth_error() -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": "auth_required",
            "message": "Подключите аккаунт Seller перед запросом данных поставщика.",
        },
    }


def _oauth_challenge(settings: Settings, *, code: str) -> CallToolResult:
    public_url = _secure_base_url(settings.public_url)
    metadata_url = (
        f"{public_url}/.well-known/oauth-protected-resource/mcp"
        if public_url
        else "/.well-known/oauth-protected-resource/mcp"
    )
    description = (
        "Authorization is required to use this Wildberries tool."
        if code == "auth_required"
        else "The access token is invalid or expired; reconnect the app."
    )
    challenge = (
        f'Bearer resource_metadata="{metadata_url}", '
        f'error="invalid_token", error_description="{description}"'
    )
    data = {
        "ok": False,
        "error": {
            "code": code,
            "message": "Подключите приложение заново и повторите запрос.",
        },
    }
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text="Для инструмента требуется подключение аккаунта Seller.",
            )
        ],
        structuredContent=data,
        isError=True,
        _meta={"mcp/www_authenticate": [challenge]},
    )


def _connection_result(data: Any, *, default_status: str) -> dict[str, Any]:
    """Return only connection handoff fields; never expose provider credentials."""
    payload = data if isinstance(data, dict) else {}
    nested = payload.get("data")
    if isinstance(nested, dict):
        payload = nested
    result: dict[str, Any] = {"ok": True}
    url = (
        payload.get("link_url")
        or payload.get("telegram_url")
        or payload.get("url")
        or payload.get("authorization_url")
    )
    if isinstance(url, str):
        safe_url = _safe_handoff_url(url, require_https=True)
        if safe_url:
            result["url"] = safe_url
    status = payload.get("status")
    result["status"] = (
        status.strip() if isinstance(status, str) and status.strip() else default_status
    )
    if isinstance(payload.get("seller_connected"), bool):
        result["seller_connected"] = payload["seller_connected"]
    suppliers = payload.get("suppliers")
    if isinstance(suppliers, list):
        result["suppliers"] = _compact(suppliers)
    if isinstance(payload.get("instructions"), str):
        result["instructions"] = payload["instructions"][:500]
    if isinstance(payload.get("expires_in"), int):
        result["expires_in"] = payload["expires_in"]
    return result


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


def _safe_handoff_url(url: Any, *, require_https: bool) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parts = urlsplit(url.strip())
        username = parts.username
        password = parts.password
        query_keys = [
            key.lower() for key, _ in parse_qsl(parts.query, keep_blank_values=True)
        ]
    except ValueError:
        return None
    if parts.scheme not in ({"https"} if require_https else {"http", "https"}):
        return None
    if not parts.netloc or username or password or parts.fragment:
        return None
    if any(
        marker in key
        for key in query_keys
        for marker in (
            "token",
            "secret",
            "password",
            "authorization",
            "cookie",
            "api_key",
            "apikey",
        )
    ):
        return None
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment)
    )


def _secure_base_url(url: Any) -> str | None:
    safe = _safe_handoff_url(url, require_https=True)
    if not safe:
        return None
    parts = urlsplit(safe)
    if parts.query or parts.fragment:
        return None
    return safe.rstrip("/")


class _SellerIdentityTokenVerifier:
    """Проверяет MCP bearer через Seller Gateway agent identity endpoint."""

    def __init__(self, gateway: SellerGatewayClient) -> None:
        self.gateway = gateway

    async def verify_token(self, token: str) -> AccessToken | None:
        if (
            not isinstance(token, str)
            or not token.strip()
            or any(character.isspace() for character in token)
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
            client_id="agent-subject",
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
                    "user_id",
                    "phone",
                    "email",
                    "address",
                    "customer",
                    "username",
                    "user_name",
                    "passport",
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
