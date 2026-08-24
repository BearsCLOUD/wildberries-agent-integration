# Публикация MCP

Compose запускает MCP-сервер по Streamable HTTP. Перед подключением ChatGPT или Claude сервер
нужно разместить рядом с сервисом аналитики, закрыть HTTPS и подключить Seller как OAuth 2.1/PKCE
identity provider. `seller.bears.ru` остаётся браузерной точкой регистрации и привязки поставщика.
Seller OAuth discovery публикует DCR для public clients ChatGPT и Claude; token exchange использует
authorization code и PKCE S256 без client secret.

Обязательные production-переменные:

- `SELLER_GATEWAY_URL=https://passport.bears.ru`
- `SELLER_IDENTITY_BRIDGE_URL=https://passport.bears.ru/mcp/identity/exchange`
- `SELLER_CONNECT_URL=https://.../integration`
- `MCP_PUBLIC_URL=https://...`
- `MCP_AUTH_ISSUER=https://passport.bears.ru`
- `OPENAI_APPS_CHALLENGE=<token из OpenAI Platform>`

Bridge принимает MCP bearer и `X-Identity-Audience: seller-gateway`, затем возвращает
короткоживущий Seller bearer вошедшего пользователя. Он обязан выдавать бесплатный agent
entitlement и сохранять проверку принадлежности пользователя и поставщика. Не задавайте
`SELLER_ACCESS_TOKEN` в публичном deployment. Контракт ответа описан в
[identity-bridge.md](../docs/identity-bridge.md).

## Production Zot

Канонический production image публикуется как
`registry.bears.ru/bearscloud/wildberries-agent-integration@sha256:<digest>`. GitOps desired state
находится только в `BearsCLOUD/bears-infra`; credentials `ci-publisher` и `prod-pull` передаются
через Infisical и не принадлежат этому репозиторию.

## Опциональный Alpic

Для воспроизводимой сборки используйте вложенный `alpic.json` и корень MCP-пакета:

```bash
npx alpic deploy \
  --root-dir ./plugins/wildberries-agent-integration \
  --runtime python3.13
```

Перед первым production deploy добавьте перечисленные выше переменные в environment Alpic.
Alpic не является identity provider: OAuth/identity bridge остаётся в Seller. После deployment
проверьте `/mcp`, OAuth metadata, отклонение неверного bearer и полный authenticated tool call.
Для OpenAI domain verification отдельно убедитесь, что выбранный hosting действительно отдаёт
`/.well-known/openai-apps-challenge`; наличие MCP endpoint само по себе этого не гарантирует.

```bash
cp plugins/wildberries-agent-integration/.env.example plugins/wildberries-agent-integration/.env
# edit the values above, then:
docker compose -f deploy/docker-compose.yml up --build -d
curl -fsS https://your-host.example/healthz
curl -fsS https://your-host.example/.well-known/oauth-protected-resource/mcp
curl -fsS https://your-host.example/.well-known/openai-apps-challenge
```

Репозиторий не заявляет, что публичный host уже запущен. DNS, TLS, OAuth-регистрация, доступ
ревьюера и production-секреты остаются отдельными операциями владельца deployment.
