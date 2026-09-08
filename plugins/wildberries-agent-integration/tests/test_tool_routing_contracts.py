from __future__ import annotations

import asyncio

from wildberries_agent_mcp.config import Settings
from wildberries_agent_mcp.server import build_server


# Prompts retained from the 2026-09-07 live ChatGPT run. They are the local
# routing regression inventory used before another browser matrix is approved.
LIVE_ROUTING_REGRESSIONS = {
    "wb_connect_supplier": "Хочу подключить свой кабинет Wildberries, помоги начать.",
    "wb_connection_status": "У меня уже подключён кабинет Wildberries? Проверь статус подключения.",
    "wb_connect_telegram": "Хочу получать уведомления по магазину в Telegram. Помоги подключить.",
    "wb_list_suppliers": "Покажи, какие кабинеты Wildberries у меня подключены.",
    "wb_analytics_summary": "Проанализируй мою торговлю на Wildberries за последнюю неделю: заказы, продажи, возвраты и расходы WB.",
    "wb_competitor_analysis": "Сравни цену товара 900000101 с похожими предложениями и скажи, дороже ли я рынка.",
    "wb_wildberries_proxy": "Покажи последние отзывы покупателей по товару 900000101 и коротко скажи, что в них важно.",
    "wb_refresh_analytics": "Обнови аналитику моего магазина за последние 7 дней, чтобы отчёты были свежими.",
    "wb_competitive_price": "Цена 1290 ₽, конкуренты 1190, 1250 и 1390 ₽, себестоимость 700 ₽: сохрани маржу 25%.",
    "wb_sales_by_region": "Покажи, в каких регионах товары лучше продавались за последние две недели и где слабее.",
    "wb_sales_weather_impact": "Проверь связь продаж товара 900000101 в Екатеринбурге с температурой за две недели.",
    "wb_seo_analytics": "Проверь SEO карточки по названию, описанию и ключевым словам и верни score.",
    "wb_warehouse_stock": "Покажи, сколько товара 900000101 осталось на складах Wildberries и где запас заканчивается.",
    "wb_unit_economics": "Цена 1200 ₽, себестоимость 320 ₽, комиссия 18%, логистика 80 ₽, налог 6%: посчитай прибыль.",
    "wb_upload_cost_price": "Установи себестоимость 320 ₽ для товара 900000101.",
    "wb_replenishment_math": "Продажи 3,2 в день, остаток 20, в пути 10, покрытие 30 дней и страховка 5: сколько отправить?",
    "wb_inventory_forecast": "Какие товары срочно пополнить и сколько отправить на склады примерно на месяц?",
}


def test_live_routing_regressions_cover_every_public_tool() -> None:
    server = build_server(Settings())
    tools = asyncio.run(server.list_tools())

    assert {tool.name for tool in tools} == set(LIVE_ROUTING_REGRESSIONS)
    assert len(set(LIVE_ROUTING_REGRESSIONS.values())) == 17
    for tool in tools:
        assert "вызывайте" in tool.description.casefold(), tool.name
        if tool.name == "wb_upload_cost_price":
            assert tool.outputSchema["title"] == "CostPriceOutput"
            assert "anyOf" in tool.outputSchema
            assert "CostPriceSuccess" in tool.outputSchema["$defs"]
            assert "CostPricePreviewFailure" in tool.outputSchema["$defs"]
            assert "CostPriceUnknownFailure" in tool.outputSchema["$defs"]
            assert "result" not in tool.outputSchema.get("properties", {})
        else:
            assert tool.outputSchema == {
                "additionalProperties": True,
                "title": f"{tool.name}DictOutput",
                "type": "object",
            }
        for field_name, field_schema in tool.inputSchema["properties"].items():
            assert field_schema.get("description"), f"{tool.name}.{field_name}"
        assert tool.meta["openai/toolInvocation/invoking"]
        assert tool.meta["openai/toolInvocation/invoked"]
        assert len(tool.meta["openai/toolInvocation/invoking"]) <= 64
        assert len(tool.meta["openai/toolInvocation/invoked"]) <= 64


def test_server_routing_policy_blocks_private_web_fallback_and_normalizes_dates() -> (
    None
):
    instructions = build_server(Settings()).instructions

    assert instructions is not None
    assert "Не используйте веб-поиск вместо закрытых данных Seller" in instructions
    assert "N завершённых календарных дней без текущего дня" in instructions
    assert "14 завершённых дней" in instructions
    assert "Всегда сообщайте точные date_from и date_to" in instructions
    assert "confirm=false" in instructions
    assert "confirm=true" in instructions
    assert "confirmation_token" in instructions


def test_specialized_tools_exclude_neighboring_intents() -> None:
    tools = {
        tool.name: tool.description
        for tool in asyncio.run(build_server(Settings()).list_tools())
    }

    assert "Для расчёта только" in tools["wb_competitor_analysis"]
    assert "резервный инструмент" in tools["wb_wildberries_proxy"]
    assert "не настраивает типы" in tools["wb_connect_telegram"]
    assert "Ничего не записывает" in tools["wb_competitive_price"]
    assert "не распределяет товар по складам" in tools["wb_replenishment_math"]
    assert "двухшаговая" in tools["wb_upload_cost_price"]
    assert "отдельного сообщения" in tools["wb_upload_cost_price"]
    assert "confirmation_token" in tools["wb_upload_cost_price"]
