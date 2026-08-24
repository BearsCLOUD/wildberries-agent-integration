# Доступ для ревьюера

Ревьюер использует полностью виртуальную sandbox. Это не Seller-аккаунт, не тестовый кабинет и не
поставщик Wildberries.

## Фиксированные значения sandbox

Значения публичны и предназначены только для выбора синтетических fixtures:

| Поле | Значение |
|---|---|
| `identity` | `reviewer-sandbox` |
| `sandbox_access_token` | `wb-agent-sandbox-token-v1` |
| `supplier_id_wb` | `900000001` |

Sandbox token не является Seller bearer или WB API token. Код sandbox обязан распознавать эти
значения до credential lookup, не обращаться к `apps/tokens-wb`, Infisical или Seller Gateway и не
отправлять запросы в Wildberries.

## Проверка

1. Загрузите [`examples/reviewer-demo.json`](../examples/reviewer-demo.json) как синтетический набор.
2. Выполните чистые расчёты и fixture-safe аналитические примеры с фиксированными значениями.
3. Убедитесь, что ответы не содержат Seller credentials, WB token или provider response body.
4. Проверьте OpenAI challenge на публичном host по инструкции в [`openai-submission.md`](openai-submission.md).

Не создавайте пользователя Seller, не запрашивайте пароль и не подключайте sandbox к боевому
поставщику. Реальный пользователь проходит обычный onboarding и вводит WB token только в Seller;
этот путь описан в [`identity-bridge.md`](identity-bridge.md).

Синтетические значения можно хранить в Git, issue и примерах: они не дают доступа к Seller или
Wildberries и никогда не должны включать реальный credential.
