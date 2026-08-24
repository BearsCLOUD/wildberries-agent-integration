# Пакет подачи в каталог OpenAI

Статус: **черновик для ручного заполнения в OpenAI Platform**. Заявка не создана и не
отправлена, а публичный MCP endpoint и домен для проверки пока не подтверждены. Этот файл
собирает значения, которые можно копировать в форму для плагина с навыками и MCP.

Официальная инструкция: [Submit plugins](https://developers.openai.com/plugins/deploy/submission).
Форма подачи: [OpenAI Platform → Plugins](https://platform.openai.com/plugins). OpenAI допускает
плагин, объединяющий MCP-сервер и навыки; форма собирает listing, MCP, skills, starter prompts,
тесты, доступность по странам и release notes.

## Значения для вкладки Info

| Поле | Значение для вставки | Примечание |
|---|---|---|
| Название | `Интеграция агента Wildberries` | Пользовательское имя из обоих manifest-файлов. |
| Короткое описание | `Русскоязычная аналитика Wildberries, SEO, карточки и прогноз пополнения через MCP.` | Короткий customer-facing текст. |
| Полное описание | `Бесплатный русскоязычный плагин для продавцов Wildberries в Codex, ChatGPT и Claude. Анализируйте продажи, конкурентов, цены и доступный разрез товар × регион; проверяйте погодные гипотезы и SEO карточки; создавайте структуру карточки, дизайн-систему и варианты фото; считайте юнит-экономику и прогнозируйте, сколько товара и куда везти. Токен поставщика вводится только в защищённом интерфейсе Seller. Выводы ограничены переданными источниками: корреляция не доказывает причинность, SEO-оценка не является прогнозом позиции.` | Не обещает полноту рынка, точный спрос или причинный эффект погоды. |
| Категория | `Analytics` | Совпадает с manifest. |
| Разработчик | `BearsCLOUD` | Выбрать только после проверки developer/business identity. |
| Website | `https://github.com/BearsCLOUD/wildberries-agent-integration` | Публичный исходный репозиторий. |
| Support URL | `https://github.com/BearsCLOUD/wildberries-agent-integration/issues` | Канал поддержки; не передавать токены в issue. |
| Privacy URL | `https://github.com/BearsCLOUD/wildberries-agent-integration/blob/main/plugins/wildberries-agent-integration/PRIVACY.md` | Перед отправкой заменить/дополнить deployment-specific privacy notice. |
| Terms URL | `https://github.com/BearsCLOUD/wildberries-agent-integration/blob/main/plugins/wildberries-agent-integration/TERMS.md` | Перед отправкой подтвердить применимые условия размещённого сервиса. |
| Логотип | `assets/logo.svg` | Оригинальный SVG готов; после публикации репозитория использовать файл или его публичный URL. |

Бесплатность означает отсутствие лицензионной, seat- или помесячной платы за функционал
плагина. Она не отменяет возможные тарифы Wildberries, внешних провайдеров и инфраструктуры.

## MCP и подключение

| Поле | Значение |
|---|---|
| Тип URL | `Universal` после появления одного рабочего endpoint для всех пользователей |
| MCP Server URL | `[BLOCKER] https://<production-mcp-host>/mcp` |
| Авторизация | Подготовленный Seller OAuth 2.1/PKCE bridge после production deployment; reviewer-ready demo credentials без MFA, SMS, email confirmation и private network |
| Регистрация нового пользователя | `https://seller.bears.ru/authentication/registration` — браузерный Seller onboarding, не MCP host |
| Domain verification | `https://<mcp-host>/.well-known/openai-apps-challenge`, ответ только точным challenge token в `text/plain` |
| CSP | Указать только реально используемые UI-домены; для текущего MCP без UI не добавлять лишние домены |

Публичный MCP должен быть размещён рядом с сервером аналитики. Модель не получает исходный
WB-токен: пользователь вводит его только в Seller, а `wb_wildberries_proxy` принимает лишь
фиксированную операцию и ограниченный payload. Это Seller Gateway, а не произвольный URL/method/
header proxy. До появления production URL, identity bridge и тестового доступа не указывать
`mcp.bears.ru` или любой другой непроверенный адрес в заявке.

Официальные требования к MCP, domain challenge, универсальному URL и annotations описаны в
[MCP server review requirements](https://developers.openai.com/plugins/deploy/app-review) и
[Security & Privacy](https://developers.openai.com/plugins/guides/security-privacy).

## Starter prompts

Вставить в форму как отдельные стартовые запросы:

1. `Покажи продажи и заказы моего Wildberries-магазина за последние 14 дней и кратко объясни тренд.`
2. `Рассчитай юнит-экономику товара: цена 1990 ₽, себестоимость 620 ₽, комиссия 18%, логистика 120 ₽, хранение 14 ₽, реклама 80 ₽, налог 6%.`
3. `Сравни цену моего товара с переданной выборкой конкурентов и предложи ценовой коридор без изменения цены.`
4. `Рассчитай, сколько товара пополнить и какие направления проверить с учётом продаж, остатков и товара в пути.`
5. `Подключи моего поставщика Wildberries через Seller; токен я введу только в браузере.`

## Ровно 5 положительных тестов

Тесты ниже предназначены для вкладки Testing. Сетевые тесты выполняются только после публикации
рабочего host и demo account; локальные расчёты не требуют доступа к Seller.

1. **Сводка продаж.** Вызвать `wb_analytics_summary` с `supplier_id_wb=123`, периодом
   `2026-08-01`—`2026-08-14` и bearer тестового владельца. Ожидается ограниченный период,
   `ok=true`, сводка и отсутствие токена/секретов в ответе.
2. **Калькулятор маржи.** Вызвать `wb_unit_economics` с ценой `1990`, себестоимостью `620`,
   комиссией `18`, логистикой `120`, хранением `14`, рекламой `80`, налогом `6`. Ожидаются
   воспроизводимые `profit`, `margin_percent` и `break_even_price`.
3. **Прогноз пополнения.** Вызвать `wb_replenishment_math` с `daily_sales=10`,
   `current_stock=30`, `target_days=14`, `safety_days=3`, `inbound_qty=20`. Ожидается
   целая неотрицательная рекомендация и раскрытые допущения.
4. **Подключение поставщика.** Вызвать `wb_connect_supplier` без токена в аргументах. Ожидается
   HTTPS-переход в Seller для регистрации/подключения и инструкция ввести токен в браузере;
   MCP не должен просить или возвращать исходный токен.
5. **Безопасный proxy-read.** Вызвать `wb_wildberries_proxy` с `supplier_id_wb=123`,
   `operation=seller_tape` и bounded payload с `nm_id`, `limit` и `page`. На настроенном
   Seller Gateway ожидается read-only ответ, supplier scope текущего владельца и отсутствие
   URL, HTTP-метода, заголовков и credential в результате.

## Ровно 3 отрицательных теста

1. **Нет авторизации.** Вызвать `wb_analytics_summary` без bearer. Ожидается `auth_required`
   либо OAuth challenge от host, без данных поставщика.
2. **Неизвестная proxy-операция.** Вызвать `wb_wildberries_proxy` с `operation=delete_everything`.
   Ожидается `proxy_operation_not_allowed` до сетевого запроса.
3. **Секрет в payload.** Вызвать `wb_wildberries_proxy` с payload вида
   `{"access_token":"secret"}`. Ожидается `proxy_payload_not_allowed`; значение секрета не
   появляется в ответе или логах.

## Аннотации инструментов

Значения должны совпадать с фактическими MCP annotations. OpenAI определяет `readOnlyHint=true`
только для чтения/вычисления без изменения состояния; `openWorldHint=true` — когда инструмент
может менять публичное состояние интернета; `destructiveHint=true` — для необратимых действий.
См. [официальную таблицу annotations](https://developers.openai.com/plugins/deploy/submission#tool-annotations).

| Инструмент | `readOnlyHint` | `openWorldHint` | `destructiveHint` | Причина |
|---|---:|---:|---:|---|
| `wb_connect_supplier` | `false` | `false` | `false` | Возвращает приватный Seller onboarding URL; сам MCP не принимает токен и не меняет публичное состояние интернета. |
| `wb_list_suppliers` | `true` | `false` | `false` | Чтение списка подключённых поставщиков. |
| `wb_analytics_summary` | `true` | `false` | `false` | Чтение аналитики за ограниченный период. |
| `wb_competitor_analysis` | `true` | `false` | `false` | Вычисление по явно переданной выборке. |
| `wb_wildberries_proxy` | `false` | `false` | `false` | Allowlist включает чтение и постановку обновления аналитики в существующую очередь Seller; arbitrary path/method/token недоступны. |
| `wb_competitive_price` | `true` | `false` | `false` | Локальный расчёт ценового коридора без записи цены. |
| `wb_sales_by_region` | `true` | `false` | `false` | Чтение и группировка доступного регионального поля. |
| `wb_sales_weather_impact` | `true` | `false` | `false` | Локальный корреляционный расчёт по переданным строкам. |
| `wb_seo_analytics` | `true` | `false` | `false` | Детерминированная проверка полноты контента, без публикации карточки. |
| `wb_warehouse_stock` | `true` | `false` | `false` | Чтение остатков через Seller Gateway. |
| `wb_unit_economics` | `true` | `false` | `false` | Чистый расчёт по входным значениям. |
| `wb_upload_cost_price` | `false` | `false` | `false` | Записывает себестоимость в закрытый аккаунт Seller; действие не является публичным или удаляющим, но меняет состояние. |
| `wb_replenishment_math` | `true` | `false` | `false` | Чистый калькулятор количества пополнения. |
| `wb_inventory_forecast` | `true` | `false` | `false` | Читает дефицит/остатки и строит рекомендацию; не меняет запасы. |

## Доступность и release notes

Предлагаемая доступность: **Россия (RU)**. Расширять список стран можно после проверки
доступности Seller/Wildberries, локальных условий и юридических материалов; не выбирать
«worldwide» по умолчанию.

Текст release notes для текущей подачи:

> Начальная подача/обновление до версии 0.1.10. Добавлены русскоязычные навыки для аналитики,
> конкурентов, ценового коридора, SEO, продаж по регионам, погодных гипотез, создания карточки,
> дизайн-системы и генерации фото. MCP получил защищённое подключение поставщика, расчёт
> юнит-экономики, калькулятор и прогноз пополнения, запись себестоимости и фиксированный
> ограниченный Seller Gateway proxy, включая постановку обновления аналитики в очередь.
> Исходные WB-токены не принимаются в чате.

## Блокеры перед Submit

- [ ] Развернуть и функционально проверить production Streamable HTTP MCP URL.
- [x] Реализовать source-контракт OAuth 2.1/PKCE, resource-bound opaque agent token и Seller
      identity exchange без нового хранилища WB credentials.
- [ ] Развернуть OAuth/identity bridge, настроить client/resource/redirect URI и выдать reviewer
      demo credentials без MFA, SMS, email confirmation и private network.
- [ ] Передать выданный порталом exact challenge token в `OPENAI_APPS_CHALLENGE`, проверить
      реализованный `/.well-known/openai-apps-challenge` на production host и подтвердить домен.
- [x] Добавить production-ready logo (`assets/logo.svg`); после push указать файл или публичный URL.
- [ ] Опубликовать deployment-specific privacy policy, terms и support contact, совпадающие с
      verified developer/business identity.
- [ ] Получить в организации OpenAI verified developer/business identity и Apps Management: Write.
- [ ] Заполнить окончательные страны доступности и policy attestations.
- [ ] После каждого deployment change повторить Scan Tools и проверить annotations, skills,
      responses и пять положительных/три отрицательных сценария.

Ни один пункт выше не считается выполненным только по наличию исходников или CI. До закрытия
блокеров нельзя писать, что плагин отправлен в каталог, одобрен или доступен в ChatGPT.
