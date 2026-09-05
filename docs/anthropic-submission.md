# Пакет подачи в каталог Claude

Статус: заявка ещё не отправлена. Публичный MCP 0.1.17 работает; через внешний HTTPS
проверены виртуальная reviewer sandbox, калькулятор и прогноз с направлениями поставки.
Проверены DCR и перенаправление на регистрацию Seller с PKCE; полный вход и подключение
поставщика через Claude Connector ещё не подтверждены. Перед подачей также требуется
сверить документы размещённого сервиса, указанные в [материалах каталога](public-listing.md).

Официальные требования: [Authentication](https://claude.com/docs/connectors/building/authentication),
[Review criteria](https://claude.com/docs/connectors/building/review-criteria) и
[Submission](https://claude.com/docs/connectors/building/submission).

## Карточка

- Название: `Интеграция агента Wildberries`.
- Описание: `Бесплатная русскоязычная аналитика Wildberries, SEO, цены и прогноз пополнения через Seller.`
- MCP URL: `https://wb.seller.bears.ru/mcp`.
- OAuth issuer: `https://passport.bears.ru`.
- Регистрация клиента: DCR, public client, authorization code, PKCE S256.
- Поддержка: `https://github.com/BearsCLOUD/wildberries-agent-integration/issues`.

## Проверка перед подачей

1. Проверьте публичные HTTPS MCP и OAuth discovery из внешней сети.
2. Подключите endpoint как Claude Custom Connector и завершите Seller onboarding.
3. Проверьте `title` и корректные read/write annotations каждого инструмента.
4. Используйте публичные sandbox fixtures из [`reviewer-access.md`](reviewer-access.md); не создавайте Seller-аккаунт и не передавайте credentials.
5. Не включайте генерацию фото в MCP-заявку: она остаётся локальным skill workflow с imagegen.

MCP не принимает WB token, URL, HTTP method или headers. `wb_wildberries_proxy` принимает только
проверенный идентификатор операции, а credential разрешает Seller по пользователю и поставщику.
