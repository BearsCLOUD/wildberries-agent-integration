---
name: wildberries-api
description: Выполняй разрешённые read-only операции Wildberries Seller API через существующий Seller credential. Используй, когда специализированного инструмента аналитики недостаточно; не принимай токен, URL, HTTP-метод или произвольный путь от пользователя.
---

# Wildberries Seller API через Seller

1. Сначала вызови `wb_wildberries_proxy` с operation `wb_api_capabilities` и пустым payload, чтобы
   получить фактический каталог доступных операций текущего deployment.
2. Выбери operation ID из ответа и вызови `wb_wildberries_proxy` с operation
   `wb_api_operation`; передай выбранный ID и только требуемые параметры в nested `payload`.
3. Не проси токен Wildberries и не конструируй host, URL, path, HTTP-метод или заголовки. Seller
   проверяет пользователя, поставщика, capability scope и сам извлекает сохранённый credential.
4. Для сводки, юнит-экономики, пополнения и записи себестоимости предпочитай специализированные
   инструменты: они дают более узкий и объяснимый контракт.
5. Указывай operation ID, источник и ограничения ответа. Не представляй пагинированный или
   усечённый результат как полную выборку.
