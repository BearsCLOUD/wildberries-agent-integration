# Public MCP contract

В deployment сервер публикует Streamable HTTP на `/mcp`; local stdio использует те же имена
инструментов. Публичный MCP размещается рядом с сервером аналитики. `seller.bears.ru`
остаётся браузерной точкой регистрации, входа и подключения поставщика, а не MCP host.

Агентский функционал бесплатен: нет лицензионной, seat- или помесячной платы за вызовы
плагина. Это не отменяет тарифы Wildberries, внешние расходы или entitlement отдельных маршрутов
Seller. Live-доступность зависит от deployment; репозиторий не фиксирует и не подтверждает
production hostname.

Для проверки домена в OpenAI Platform deployment отдаёт значение
`OPENAI_APPS_CHALLENGE` точным plain-text ответом на
`GET /.well-known/openai-apps-challenge`. Если переменная не задана или содержит пробелы, маршрут
отвечает `404`; токен проверки не хранится в репозитории.

## Auth and ownership

Инструменты с данными поставщика требуют Seller bearer. В production identity bridge обменивает
bearer агента на короткоживущий Seller bearer. Сырой токен Wildberries не попадает в аргументы,
ответы или логи MCP. Seller Gateway проверяет authenticated owner, supplier scope и доступ к
каждой операции.

Hosted HTTP на отсутствующий bearer отвечает `401` с `WWW-Authenticate`. Local stdio и
незащищённые development-вызовы используют стабильную object form:

```json
{
  "ok": false,
  "error": {"code": "auth_required"}
}
```

Provider response bodies and credentials are intentionally omitted from errors.

## Fixed Seller Gateway proxy

`wb_wildberries_proxy` is a public MCP tool for a fixed Seller Gateway contract. It accepts only
allowlisted reads and the bounded analytics refresh queue operation:

```json
{
  "supplier_id_wb": 123,
  "operation": "competitor_cards",
  "payload": {"nm_id": 456789}
}
```

The model cannot supply a token, host, URL, path, HTTP method, or headers. `operation` must be in the
server allowlist, and `payload` is validated and bounded for that operation before any network call.
Unknown operations return `proxy_operation_not_allowed`; sensitive-looking payload keys are rejected.
Seller Gateway remains responsible for authenticated ownership, supplier scope, route availability,
and the stored Wildberries credential. Source support does not prove live acceptance by a particular
production deployment.

Текущий allowlist операций: `competitor_cards`, `competitor_orders`, `card_details`, `card_photos`,
`price_block`, `feedbacks`, `feedback_average`, `wb_api_capabilities`, `wb_api_operation`,
`seller_tape`, `analytics_refresh`, `analytics_refresh_status`, `kt_statistics_period`,
`kt_statistics_grouped`, `promotion_list` и `promotion_details`. `analytics_refresh` только
ставит существующую задачу аналитики в очередь Seller и не изменяет данные Wildberries;
`analytics_refresh_status` читает состояние этой задачи. Для остальных операций
сохраняются supplier scope и bounded payload. Для
`wb_api_capabilities` сервер сам строит `GET /suppliers/{supplier_id_wb}/wb/capabilities`.
Для `wb_api_operation` агент передаёт только проверенный идентификатор операции и данные:

```json
{
  "supplier_id_wb": 123,
  "operation": "wb_api_operation",
  "payload": {
    "operation_id": "stats.orders",
    "payload": {"date_from": "2026-08-01", "date_to": "2026-08-24"}
  }
}
```

Идентификатор ограничен шаблоном `[a-z0-9_.-]{1,80}`, а фактический маршрут и метод выбирает
Seller Gateway. Write-маршруты Wildberries, удаление кампаний и произвольные WB paths в allowlist
не входят.

## Competitor analysis

`wb_competitor_analysis` uses an authenticated supplier scope but analyzes only explicit comparable
rows. It does not search for competitors itself:

```json
{
  "supplier_id_wb": 123,
  "nm_id": 456789,
  "competitor_rows": [
    {"nm_id": 700001, "sale_price": 1890},
    {"nm_id": 700002, "sale_price": 2050}
  ],
  "seller_price": 1990,
  "target_position": "median"
}
```

With no `competitor_rows`, the tool returns `source_required`. A successful response identifies
`source="provided_rows"` and returns `competitor_count`, `excluded_count`, `source_row_count`,
`malformed_row_count`, `price_corridor`, `position`, and a caveat. The result describes the supplied
sample only. It does not reveal or infer competitor sales, conversion, advertising spend, inventory
history, market share, or unit economics.

## Competitive price

`wb_competitive_price` is a local calculation and does not write a price or discount:

```json
{
  "seller_price": 1990,
  "competitor_prices": [1790, 1890, 2050, 2190],
  "cost_price": 900,
  "target_margin_percent": 25,
  "target_position": "median"
}
```

The response includes the valid sample count, excluded values, min/max/average/median, a
25th–75th-percentile `price_corridor`, `position`, `corridor_target_price`, optional
`minimum_viable_price`, and `target_price`. The optional cost floor excludes commissions, logistics,
tax, storage, advertising, and other costs. The corridor is not a demand or profitability estimate;
use `wb_unit_economics` with complete inputs before a price decision.

## Product × region

`wb_sales_by_region` requires `supplier_id_wb`, ISO dates in `date_from` and `date_to`, and either
explicit `rows` or an `nm_id`:

```json
{
  "supplier_id_wb": 123,
  "nm_id": 456789,
  "date_from": "2026-08-01",
  "date_to": "2026-08-14"
}
```

When `rows` are omitted, the tool reads only the fixed Seller route
`GET /statistics/tape/v2?supplier_id_wb&nm_id&limit&page`, then filters the bounded result to the
requested period. `/statistics/report/combined` does not provide a region field and is not used as
a product-by-region source. With neither `rows` nor `nm_id`, the tool returns `source_required`.

The response reports `source`, `period`, `nm_id`, `regions`, `totals`, `source_row_count`, and
`skipped_row_count`. Region means the geographic field actually present in a row. The tool does not
turn a warehouse, logistics hub, or deficit district into a buyer region and does not replace missing
regional data with a guess.

## Weather and sales

`wb_sales_weather_impact` is a local calculation over supplied rows:

```json
{
  "region": "Moscow",
  "sales_rows": [
    {"date": "2026-08-01", "region": "Moscow", "sales": 12}
  ],
  "weather_rows": [
    {"date": "2026-08-01", "region": "Moscow", "temperature_c": 24.1}
  ]
}
```

Rows are joined by compatible date and region. The result reports `matched_observations`, `status`,
`observation_count`, `correlation`, `direction`, `strength`, and a caveat. Fewer than four usable
observations return `insufficient_data`; missing variation returns `insufficient_variation`.

Correlation does not establish that weather caused a sales change. Seasonality, weekday, promotion,
price, stock availability, geography, and other confounders may explain the relationship. The tool
does not fetch weather by itself, does not replace missing weather with zeroes, and does not forecast
sales.

## SEO analytics

`wb_seo_analytics` is a deterministic content-completeness check:

```json
{
  "title": "Термокружка из нержавеющей стали 450 мл",
  "description": "Двустенная термокружка для горячих и холодных напитков.",
  "keywords": ["термокружка", "450 мл"],
  "characteristics": {"материал": "нержавеющая сталь", "объём": "450 мл"},
  "competitor_titles": ["Термокружка 450 мл"]
}
```

The response includes `score`, `max_score`, a transparent `breakdown`, input `metrics`,
`suggestions`, and `competitor_benchmark`. The benchmark compares only title lengths in the explicit
sample. The score is not a Wildberries ranking prediction and does not observe query frequency,
impressions, CTR, conversion, advertising traffic, or marketplace algorithms.

## Unit economics

`wb_unit_economics` has no Seller credentials and is safe to run on synthetic data:

```json
{
  "price": 1990,
  "cost_price": 620,
  "commission_percent": 18,
  "logistics_per_unit": 120,
  "storage_per_unit": 14,
  "advertising_per_unit": 80,
  "tax_percent": 6,
  "discount_percent": 10,
  "target_margin_percent": 25
}
```

The result includes `net_price`, `profit`, `margin_percent`, `break_even_price`,
`target_margin_price`, and the assumptions used.

## Forecast

`wb_inventory_forecast` accepts a supplier ID and optional `nm_ids`, then reads the Seller deficit
and optional warehouse-stock route. The response includes `recommended_qty`, `destinations`,
`district_demand`, `warehouse_stock_status`, and warnings. When warehouse stock is unavailable,
`destinations[].destination_type` is `district` and the allocation is explicitly a regional-demand
heuristic.

## Cost-price write

`wb_upload_cost_price` changes the cost price of one `nm_id` in Seller. It accepts `supplier_id_wb`,
`nm_id`, and `cost_price` and executes immediately when bearer and ownership checks pass. Bearer and
Wildberries token are not tool arguments. This is the only write tool described by this contract;
price and discount writes remain out of scope.
