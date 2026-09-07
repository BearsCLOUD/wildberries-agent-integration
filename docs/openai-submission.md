# Пакет подачи в каталог OpenAI

Статус: production MCP, Seller OAuth 2.1/PKCE и reviewer sandbox функционально проверены.
Заявка не отправлена. Перед отправкой нужно создать черновик в OpenAI Platform, получить и
разместить domain challenge, повторить Scan Tools и завершить business verification.

Официальная инструкция: [Submit plugins](https://developers.openai.com/plugins/deploy/submission).
Форма: [OpenAI Platform → Plugins](https://platform.openai.com/plugins).

## Импортируемые файлы

- `plugins/wildberries-agent-integration/chatgpt-app-submission.json` — 17 инструментов,
  обоснования annotations, ровно 5 положительных и 3 отрицательных теста;
- `plugins/wildberries-agent-integration/assets/logo-1024.png` — квадратный логотип 1024×1024;
- каталог `plugins/wildberries-agent-integration/skills` — 16 навыков;
- публичные legal URL: `https://wb.seller.bears.ru/privacy` и
  `https://wb.seller.bears.ru/terms`;
- поддержка: `https://wb.seller.bears.ru/support`.

## App Info

| Поле | Значение |
|---|---|
| Название | `Интеграция агента Wildberries` |
| Subtitle | `Аналитика продавца WB` |
| Категория | `BUSINESS` |
| Website | `https://wb.seller.bears.ru/` |
| Support | `https://wb.seller.bears.ru/support` |
| Privacy | `https://wb.seller.bears.ru/privacy` |
| Terms | `https://wb.seller.bears.ru/terms` |
| MCP URL | `https://wb.seller.bears.ru/mcp` |
| OAuth scope | `wildberries-agent-free` |

Описание импортируется из `chatgpt-app-submission.json`. Оно описывает только фактические
возможности: аналитику Seller/Wildberries, локальные расчёты, прогноз пополнения и подтверждаемую
запись себестоимости. Публикация карточек, цен, ответов на отзывы и заказов в текущую поверхность
не входят.

## Организация

- Полное наименование: `ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ «ОУПЕН ГРУПП»`;
- Сокращённое наименование: `ООО «ОУПЕН ГРУПП»`;
- ИНН: `6679173759`;
- КПП: `667101001`;
- ОГРН: `1246600007543` от `16.02.2024`;
- Юридический адрес: `620014, Свердловская область, г. Екатеринбург, ул. Добролюбова, стр. 3, офис 206`;
- Генеральный директор: `ХУСНУТДИНОВ КИРИЛЛ ЕВГЕНЬЕВИЧ`;
- E-mail: `OFFICE@NR66.RU`;
- телефон: `+7 (992) 092-00-00`.

Банковские реквизиты не относятся к карточке приложения и не загружаются без отдельного запроса
площадки. Для business verification использовать только официальный документ, который прямо
запросит OpenAI; самостоятельно созданная карточка предприятия не заменяет государственный или
банковский документ.

## MCP и reviewer access

- Universal Streamable HTTP URL: `https://wb.seller.bears.ru/mcp`;
- OAuth authorization server: `https://passport.bears.ru/`;
- dynamic client registration и PKCE S256 включены;
- access token TTL: 1 час; rotating refresh token TTL: 90 дней;
- реальный пользователь получает anonymous agent token и связывает его с Seller через одноразовый
  link code; Wildberries token вводится только в Seller;
- reviewer выбирает режим `Демо для проверки` на странице согласия OAuth;
- reviewer token и supplier являются публичными синтетическими значениями; sandbox не делает
  запросы к Seller, базе данных или Wildberries и не меняет внешнее состояние.

## Domain verification

После создания черновика и ввода MCP URL OpenAI выдаёт challenge. Его точное значение нужно
передать в runtime-переменную `OPENAI_APPS_CHALLENGE`; оно не хранится в Git. После deployment
`https://wb.seller.bears.ru/.well-known/openai-apps-challenge` должен отвечать этим значением как
plain text. До получения challenge маршрут намеренно отвечает `404`.

## Testing

Пять положительных тестов импортируются из JSON и проверяют:

1. `wb_connection_status` — состояние связи Seller и список поставщиков;
2. `wb_analytics_summary` — аналитику `900000001` за `2026-08-01`—`2026-08-14`;
3. `wb_inventory_forecast` — прозрачную рекомендацию пополнения;
4. `wb_unit_economics` — детерминированный расчёт без авторизации;
5. `wb_upload_cost_price` — подтверждённую, но полностью симулированную demo-запись.

Для пятого кейса первый вызов всегда выполняется с `confirm=false`. Ревьюер получает точные
`supplier_id_wb`, `nm_id` и сумму, отдельно подтверждает их следующим сообщением, после чего
повторный вызов с `confirm=true` возвращает синтетический результат без внешнего изменения.

Три отрицательных теста имеют `tools_triggered: null`: прогноз погоды, удаление карточки WB и
публикация ответа на отзыв. Они не должны запускать приложение.

## Availability и release notes

Выбрать: Казахстан, Армения, Кыргызстан, Узбекистан, Грузия и Таджикистан.

Release notes:

> Первый публичный beta-релиз: 17 MCP-инструментов и 16 русскоязычных навыков для аналитики
> продавца Wildberries, безопасного подключения Seller, юнит-экономики и прогноза пополнения.
> Два калькулятора доступны без входа; остальные операции используют OAuth. Reviewer sandbox
> полностью виртуален и не меняет данные Seller или Wildberries.

## Starter prompts

1. `Проанализируй мою торговлю на Wildberries за последние 14 дней: продажи, заказы, возвраты и основные выводы.`
2. `Какие товары нужно срочно пополнить и сколько отправить на склады, чтобы хватило примерно на месяц?`
3. `Посчитай прибыль и маржу по товару с учётом цены, себестоимости, комиссии, логистики и налога.`

## Финальная остановка

После зелёного Scan Tools, подтверждённого домена, загруженных файлов, заполненных 5+3 тестов и
business verification оставить заявку в состоянии draft. Кнопку отправки на review не нажимать
без отдельного указания оператора.
