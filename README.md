# Интеграция агента Wildberries

[![CI](https://github.com/BearsCLOUD/wildberries-agent-integration/actions/workflows/ci.yml/badge.svg)](https://github.com/BearsCLOUD/wildberries-agent-integration/actions/workflows/ci.yml)
[![Релиз](https://img.shields.io/github/v/release/BearsCLOUD/wildberries-agent-integration)](https://github.com/BearsCLOUD/wildberries-agent-integration/releases)
[![Звёзды](https://img.shields.io/github/stars/BearsCLOUD/wildberries-agent-integration)](https://github.com/BearsCLOUD/wildberries-agent-integration)

Бесплатный MCP-плагин для продавцов Wildberries в Codex, Claude и других MCP-клиентах.

От вопроса к проверяемому числу и следующему действию:

- читайте продажи, заказы, финансы, цены и остатки через аккаунт Seller;
- считайте комиссию, логистику, налог, маржу и цену безубыточности;
- прогнозируйте пополнение и показывайте распределение по складам или регионам;
- запускайте подключение поставщика через существующий браузерный сценарий Seller.

Агентский функционал предоставляется бесплатно: у плагина нет лицензионной, seat- или
помесячной платы за вызовы. Identity bridge выдаёт бесплатный доступ агенту без проверки платного
тарифа; Seller всё равно проверяет личность пользователя и принадлежность поставщика. Тарифы
Wildberries и инфраструктурные расходы остаются отдельными.

## Граница безопасности

В production MCP-сервер обменивает bearer агента через `SELLER_IDENTITY_BRIDGE_URL` и получает
короткоживущий Seller bearer для текущего пользователя. В шлюз передаётся только этот bearer.
Исходный токен агента и токен Wildberries никогда не попадают в URL, логи, файлы, аргументы
инструментов или результаты MCP. Токен поставщика вводится только в Seller:

`Интеграция → Добавить поставщика → Персональный API-токен`

Релиз ориентирован на чтение и расчёты. Единственная запись — установка явно указанной себестоимости;
цены, скидки и настройки поставщика не меняются.

## Инструменты

| Инструмент | Назначение | Авторизация |
| --- | --- | --- |
| `wb_connect_supplier` | Открыть безопасное подключение поставщика | Браузерный сценарий |
| `wb_list_suppliers` | Показать поставщиков текущего пользователя | Seller bearer |
| `wb_analytics_summary` | Продажи и заказы, с доступным финансовым и ценовым обогащением | Seller bearer |
| `wb_warehouse_stock` | Остатки Wildberries по `nm_id` и складам | Seller bearer |
| `wb_upload_cost_price` | Записать явно указанную себестоимость товара в Seller | Seller bearer |
| `wb_unit_economics` | Калькулятор маржи и безубыточности | Не требуется |
| `wb_replenishment_math` | Быстрый расчёт количества пополнения | Не требуется |
| `wb_inventory_forecast` | Прогноз количества и направлений пополнения | Seller bearer |

Запись себестоимости выполняется сразу по явно указанным поставщику, `nm_id` и сумме и меняет
только выбранный `nm_id` в Seller. Прогноз возвращает период, формулу, распределение, статус источников и предупреждения. Это
рекомендация для планирования, а не гарантия будущего спроса. При отсутствии складских данных
направления помечаются как региональная эвристика.

## Локальная разработка

```bash
cd plugins/wildberries-agent-integration
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
export SELLER_GATEWAY_URL=http://127.0.0.1:8000
export SELLER_CONNECT_URL=https://seller.example.com/integration
wildberries-agent-mcp
```

Для локального MCP-клиента используйте комплектный `.mcp.json`. Для HTTP-сервера:

```bash
wildberries-agent-mcp --transport streamable-http --host 0.0.0.0 --port 8080
```

Production требует HTTPS и OAuth 2.1/PKCE identity bridge. Задайте
`SELLER_IDENTITY_BRIDGE_URL`, `MCP_PUBLIC_URL` и `MCP_AUTH_ISSUER`; без bridge production/staging
запросы завершаются fail-closed. `MCP_PUBLIC_URL` — адрес публичного MCP рядом с сервером
аналитики, а `seller.bears.ru` используется только для регистрации/входа и добавления поставщика.
Публичный адрес аналитического MCP намеренно не зашит в репозиторий.

Бесплатная агентская поверхность включает статистику, список поставщиков, калькуляторы, запись
себестоимости и прогноз дефицита. Если конкретный старый маршрут аналитики ещё не опубликован,
плагин возвращает понятное предупреждение; это не превращается в платный экран. Если маршрут
складских остатков не опубликован, прогноз использует региональный спрос и явно отмечает эвристику.

## Codex и Claude

Канонический исходник плагина находится в `plugins/wildberries-agent-integration` и содержит
manifest для Codex и Claude. Codex использует запись `.agents/plugins/marketplace.json`, Claude —
`claude/mcp.json` с `${CLAUDE_PLUGIN_ROOT}`. Перед публичной подачей прочитайте
[инструкции для каталога](docs/public-listing.md).

## Карта исходников

Адаптер использует существующие маршруты Seller, не публикуя внутренние сервисы напрямую:

- `/suppliers`;
- `/statistics/report/combined`;
- `/statistics/orders`;
- `/financial_report/dashboard/v2` (если разрешено entitlement);
- `/price_management` (если разрешено entitlement);
- `/price_management/stocks-report/wb-warehouses` (складской адаптер с региональным fallback).

См. [SPEC.md](SPEC.md), [контракт MCP](docs/mcp-contract.md) и
[контракт identity bridge](docs/identity-bridge.md). Перед каталогом опубликуйте
[уведомление о приватности](plugins/wildberries-agent-integration/PRIVACY.md),
[условия](plugins/wildberries-agent-integration/TERMS.md) и
[канал поддержки](plugins/wildberries-agent-integration/SUPPORT.md).

## Лицензия

MIT. Подробности — в [LICENSE](LICENSE).
