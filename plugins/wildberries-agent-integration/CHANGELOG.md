# Changelog

## 0.1.25

- Региональный отчёт использует дневную агрегацию Seller вместо ограниченной ленты заказов.
- Количество и сумма записей Sales имеют отдельные названия; возвраты и сторно не выдаются за чистые продажи.
- Региональный навык вызывает специализированный инструмент; ручные выборки сохраняют прежний формат.

## 0.1.24

- Погодный анализ использует дневной региональный отчёт Seller вместо ограниченной ленты заказов.
- Метрика `sales_records` явно обозначает число записей, включая возвраты и сторно, а не чистые продажи.
- Выбранный регион передаётся источнику; несовместимый ответ Seller возвращает ошибку вместо пустой статистики.

## 0.1.23

- Погодный анализ читает продажи из Seller по поставщику, товару и периоду, если агент не передал свой ряд.
- В результате указаны ограничения выборки и источник региона; пропуски не подменяются нулевыми продажами.
- Погодный навык использует новый способ чтения; виртуальная песочница не обращается к Seller.

## 0.1.22

- Размер складского варианта определяется по артикулу и chrtId из существующих карточек Seller.
- Повторяющиеся строки одного склада объединяются перед распределением пополнения.
- При недоступности карточек сохраняется региональный вариант прогноза и статус ограничения.

## 0.1.21

- Прогноз учитывает запрошенный горизонт при известных продажах, а исходный дефицит Seller показывает отдельно.
- Размер товара сохраняется в результате; остатки другого или неизвестного размера не используются для складского распределения.

## 0.1.20

- Анализ конкурентов возвращает до 20 пар «артикул — цена» и число оставшихся карточек; ценовые итоги рассчитываются по всей выборке.
- Пояснения ценового коридора и ограничений расчёта переведены на русский язык.

## 0.1.19

- Анализ конкурентов получает похожие товары через существующий источник Seller, если строки не переданы агентом.
- Ручная выборка сохраняет приоритет; пустой ответ источника не означает отсутствие конкурентов.
- Навык анализа конкурентов использует автоматический источник; виртуальная песочница остаётся без сетевых вызовов.

## 0.1.18

- Claude подключается к публичному HTTPS MCP без локального Python-сервера.
- Инструкции установки описывают авторизацию Seller в браузере.
- Публичный MCP продолжает работать на версии 0.1.17; этот выпуск обновляет клиентский пакет.

## 0.1.17

- Пояснения калькулятора пополнения, причины распределения по складам и предупреждения прогноза переведены на русский язык.

## 0.1.16

- Исправлено обрезание названий складов и количества товара в направлениях прогноза пополнения.
- Добавлена проверка сохранности направлений поставки в виртуальной песочнице.

## 0.1.15

- Added a fixed virtual reviewer sandbox with public synthetic identity, token, and supplier values.
- Kept sandbox analytics, proxy reads, queue refresh, and cost-price writes deterministic and free of external effects.
- Documented the OpenAI domain challenge flow and removed the obsolete reviewer-account requirement.

## 0.1.14

- Removed the invalid Codex-local MCP declaration that broke `codex exec` during plugin loading.
- Kept Codex distribution skills-only until OpenAI issues a registered remote app ID for the hosted MCP.
- Documented `https://wb.seller.bears.ru/mcp` as the verified production endpoint without adding a second credential or analytics backend.

## 0.1.13

- Added separate, fully synthetic reviewer inputs without copying Seller or Wildberries credentials.
- Documented separate OpenAI and Anthropic directory handoffs for the same Russian MCP integration.
- Aligned the submission pack with Seller OAuth dynamic client registration and PKCE S256.
- Kept production deployment on the canonical Bears Zot registry path; runtime readiness remains a separate check.

## 0.1.12

- Added an explicit `wildberries-agent-free` OAuth security scheme to every MCP tool for ChatGPT account linking.
- Propagated the opaque agent bearer for Gateway-side subject, resource, and free-entitlement validation on finance and price reads.
- Bound existing Seller sessions to OAuth authorization state while preserving anonymous registration handoff for new users.
- Kept Seller as the only credential and analytics backend; the public MCP remains a thin authenticated client.

## 0.1.11

- Split analytics refresh into an explicit bounded write tool and restored truthful read-only proxy annotations.
- Validate public MCP bearer tokens through the Seller identity bridge before exposing authenticated tools.
- Aligned OAuth metadata with the free `wildberries-agent-free` scope used by Seller.
- Added deterministic Alpic build and start configuration for the nested MCP package.

## 0.1.10

- Added the exact OpenAI domain-verification challenge route for a production deployment.
- Added bounded review and rating reads through the existing Seller Gateway plus a Russian review-analysis skill.
- Added a Russian skill for capability-driven read-only Wildberries Seller API operations.
- Added a Russian OpenAI Plugins Directory submission pack, reviewer scenarios, and listing copy.
- Reworked the repository presentation around free agent analytics, replenishment, and secure Seller ownership.

## 0.1.9

- Added Russian skills for competitor analysis, competitive pricing, regional sales, weather impact,
  SEO analytics, product-card creation, design systems, and product-photo generation.
- Added bounded read-only MCP tools for competitor context, price corridors, regional sales, weather
  hypotheses, SEO completeness, and fixed Seller Gateway operations.
- Kept provider credentials server-side and standardized all public package versions on plain SemVer.

## 0.1.8

- Removed the extra confirmation round-trip from `wb_upload_cost_price`; explicit tool arguments now execute immediately within Seller ownership.

## 0.1.7

- Made `wb_connect_supplier` open new-user registration at `seller.bears.ru` without an MCP bearer or extra confirmation.
- Documented the analytics server as the public MCP host; Seller remains the browser onboarding service.

## 0.1.6

- Made cost-price writes return a canonical status only after Seller echoes the requested `nm_id` and amount.
- Added an explicit unknown-write outcome for empty, mismatched, timeout, or server-error responses.

## 0.1.5

- Added focused tests proving cost-price confirmation, bearer fail-closed behavior, and payload redaction.

## 0.1.4

- Added `wb_upload_cost_price`, a confirmation-gated tool for writing one product cost price to Seller.
- Added the Russian `cost-price-upload` skill with explicit confirmation guidance.

## 0.1.3

- Added a dedicated replenishment calculator skill for fast, transparent quantity planning.
- Localized catalog descriptions, MCP tool metadata, skills, and public README to Russian.
- Standardized published manifests on plain SemVer without build or cachebuster suffixes.

## 0.1.2

- Added a Claude-specific MCP config using `${CLAUDE_PLUGIN_ROOT}` while keeping Codex's local config separate.
- Published the identity-bridge and free-entitlement contract for hosted deployments.

## 0.1.1

- Added fail-closed HTTPS and handoff URL validation.
- Made optional finance/price enrichment non-blocking for the free core analytics flow.
- Added regional-demand allocation when warehouse stock is not exposed by the gateway.
- Corrected MCP tool annotations and protected-resource metadata validation.

## 0.1.0

- Added Codex and Claude plugin manifests.
- Added Streamable HTTP and local stdio MCP transports.
- Added supplier handoff, analytics summary, warehouse stock, unit economics, replenishment math, and inventory forecast tools.
- Added four concise agent skills and security guidance.
