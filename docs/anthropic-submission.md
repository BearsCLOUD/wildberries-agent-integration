# Пакет подачи в каталог Claude

Статус: черновик до публикации production MCP и отдельной учётной записи ревьюера.

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
4. Передайте отдельные credentials ревьюера только в закрытой форме каталога.
5. Не включайте генерацию фото в MCP-заявку: она остаётся локальным skill workflow с imagegen.

MCP не принимает WB token, URL, HTTP method или headers. `wb_wildberries_proxy` принимает только
проверенный идентификатор операции, а credential разрешает Seller по пользователю и поставщику.
