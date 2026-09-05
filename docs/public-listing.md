# Публичное описание и подготовка каталога

Статус: исходники плагина подготовлены, но заявка в каталог OpenAI не создана и не отправлена.
В официальном MCP Registry опубликована версия `0.1.26` со статусом `active` (проверено 5 сентября 2026).
Имя: `io.github.BearsCLOUD/wildberries-agent-integration`; подключение: `https://wb.seller.bears.ru/mcp`.
[Публичная запись Registry](https://registry.modelcontextprotocol.io/v0.1/servers/io.github.BearsCLOUD%2Fwildberries-agent-integration/versions/0.1.26).
Эта публикация не означает одобрение в каталогах ChatGPT или Claude.
Публичный MCP host, deployment подготовленного Seller OAuth bridge, виртуальная reviewer sandbox и
домен проверки должны быть подтверждены отдельно. Поля для копирования, тесты и список блокеров собраны в
[пакете подачи OpenAI](openai-submission.md).

## Позиционирование

**Интеграция агента Wildberries** — бесплатный русскоязычный плагин для Codex, ChatGPT и
Claude: MCP-сервер и навыки для продавца Wildberries. Он объединяет аналитику продаж, заказов,
цен, остатков и отзывов с калькулятором юнит-экономики, прогнозом пополнения и направлений, SEO карточки,
сравнением конкурентов, региональным разрезом, проверкой погодных гипотез, созданием карточки,
дизайн-системой и генерацией фото.

Короткое описание для карточки:

> Русскоязычная аналитика Wildberries, SEO, карточки и прогноз пополнения через MCP.

Полное описание для карточки:

> Бесплатный русскоязычный плагин для продавцов Wildberries в Codex, ChatGPT и Claude.
> Анализируйте продажи, конкурентов, цены и доступный разрез «товар × регион»; проверяйте
> погодные гипотезы и SEO карточки; создавайте структуру карточки, дизайн-систему и варианты
> фото; считайте юнит-экономику и прогнозируйте, сколько товара и куда везти. Токен поставщика
> вводится только в защищённом интерфейсе Seller. Выводы ограничены переданными источниками:
> корреляция не доказывает причинность, SEO-оценка не является прогнозом позиции.

Рекомендуемые поисковые ключи: `wildberries`, `аналитика Wildberries`, `конкуренты`, `сравнение
цен`, `SEO Wildberries`, `карточка товара`, `дизайн-система`, `генерация фото`, `продажи по
регионам`, `погода и продажи`, `юнит-экономика`, `прогноз пополнения`, `MCP`, `Codex`, `Claude`.
Использовать их естественно, без переспама.

«Бесплатно» означает отсутствие лицензионной, seat- или помесячной платы за функционал плагина.
Это не отменяет возможные тарифы Wildberries, внешних провайдеров и инфраструктуры.

## Канонические ссылки

- Репозиторий: <https://github.com/BearsCLOUD/wildberries-agent-integration>
- Поддержка: <https://github.com/BearsCLOUD/wildberries-agent-integration/issues>
- Privacy draft: <https://github.com/BearsCLOUD/wildberries-agent-integration/blob/main/plugins/wildberries-agent-integration/PRIVACY.md>
- Terms draft: <https://github.com/BearsCLOUD/wildberries-agent-integration/blob/main/plugins/wildberries-agent-integration/TERMS.md>
- Браузерная регистрация Seller: <https://seller.bears.ru/authentication/registration>
- MCP contract: [docs/mcp-contract.md](mcp-contract.md)
- Identity bridge contract: [docs/identity-bridge.md](identity-bridge.md)
- Пакет подачи: [docs/openai-submission.md](openai-submission.md)

Действующие документы Seller: [политика обработки персональных данных](https://seller.bears.ru/privacy-policy)
и [пользовательские условия](https://seller.bears.ru/contract). Публичный API Seller возвращает оба
документа версии 1; в них указан оператор ООО «ИНТЕРНЕТ МЕДВЕДИ».
Соглашение описывает платные тарифы; отдельные условия бесплатного агентского доступа и передачи
аналитики подключённому AI-клиенту требуют сверки перед использованием этих ссылок в заявке.

Privacy и Terms репозитория сейчас описывают адаптер и требования к hosted deployment. Перед подачей нужно
опубликовать точные controller, retention, deletion, subprocessors, support и jurisdiction для
фактического размещения.

## OpenAI / ChatGPT

Официальный путь — [Submit plugins](https://developers.openai.com/plugins/deploy/submission) и
[OpenAI Platform → Plugins](https://platform.openai.com/plugins). Для этого репозитория нужен
вариант **With MCP**, объединяющий MCP и загружаемые/импортируемые навыки. Форма требует listing,
MCP URL, доменную проверку, annotations всех tools, starter prompts, ровно пять положительных и
три отрицательных теста, доступность по странам и release notes.

Публичная подача должна использовать один рабочий Universal Streamable HTTP URL:
`https://wb.seller.bears.ru/mcp`. `seller.bears.ru` — только браузерный onboarding; не указывайте
его как MCP host.

Домен MCP должен вернуть только выданный OpenAI challenge token по
`/.well-known/openai-apps-challenge`. Получите token в OpenAI Platform: **Create plugin → With MCP**,
укажите `https://wb.seller.bears.ru/mcp`, дождитесь **Domain not verified** и разверните выданное
значение на `https://wb.seller.bears.ru/.well-known/openai-apps-challenge`. Не указывайте `mcp.bears.ru` или другой адрес без
функциональной проверки deployment. До закрытия блокеров нельзя писать, что плагин отправлен,
одобрен или доступен в ChatGPT.

Полезные официальные материалы:

- [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- [Submit plugins](https://developers.openai.com/plugins/deploy/submission)
- [MCP server review requirements](https://developers.openai.com/plugins/deploy/app-review)
- [Security & Privacy](https://developers.openai.com/plugins/guides/security-privacy)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)

## Claude и Codex

Claude Code проверяет каталог командой:

```bash
claude plugin validate plugins/wildberries-agent-integration
```

Claude Connector и ChatGPT требуют опубликованный HTTPS Streamable HTTP endpoint с корректной
аутентификацией. Claude Desktop/Code использует
`plugins/wildberries-agent-integration/claude/mcp.json`; Codex — тот же публичный endpoint через
`plugins/wildberries-agent-integration/.mcp.json`. Обе конфигурации используют существующий Seller
OAuth и не создают локального credential/backend contour.

## Границы и безопасность

- Токен Wildberries никогда не передаётся в MCP-аргументах, ответах или логах. Пользователь
  вводит его только в Seller.
- `wb_wildberries_proxy` — фиксированный read-only Seller Gateway allowlist. Агент не задаёт
  URL, HTTP-метод, путь, заголовки или credential; write-маршруты и удаление кампаний исключены.
- `wb_refresh_analytics` — отдельная bounded-операция постановки обновления статистики в
  существующую очередь Seller.
- `wb_upload_cost_price` — единственная явная запись бизнес-данных: себестоимость выбранного
  `nm_id` в Seller после проверки bearer и supplier ownership; отдельная queue-операция только
  запускает пересчёт аналитики.
- SEO — прозрачная эвристика полноты контента, не гарантия позиции. Погодный результат —
  корреляция по сопоставленным строкам, не доказательство причинности и не прогноз.
- Конкурентный и региональный анализ ограничен фактически доступным источником; отсутствие строк
  возвращает `source_required`, а не выдуманные значения.
- Органический рост звёзд и пользователей не автоматизируется.

## Принятие перед подачей

Подача возможна только после появления production MCP URL, deployment OAuth/identity bridge, виртуальной
reviewer sandbox, challenge token, публичного URL готового логотипа, deployment-specific legal URLs,
verified developer/business identity, выбранных стран и повторного Scan Tools. Полный список и
ровно 5+3 тестов находятся в [пакете подачи](openai-submission.md).
