# Identity bridge contract

The plugin intentionally does not implement a user database or a Wildberries-token store. A hosted
deployment supplies a small OAuth 2.1/PKCE identity bridge at `SELLER_IDENTITY_BRIDGE_URL`.

## Exchange

The MCP server sends:

```http
POST /mcp/identity/exchange
Authorization: Bearer <agent-access-token>
X-Identity-Audience: seller-gateway
X-Request-ID: <opaque-request-id>
```

The bridge validates the agent token, maps its subject to the existing Seller user, and returns a
short-lived Seller bearer. The agent surface is free for every connected Seller user: the bridge
must not require a paid plan, seat, or per-call charge. Seller still enforces identity and supplier
ownership before returning data or accepting a write:

```json
{
  "access_token": "<short-lived-seller-bearer>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "analytics:read supplier:read supplier:connect cost_price:write",
  "entitlements": ["wildberries-agent-free"]
}
```

The plugin also accepts `seller_access_token` for compatibility with an existing bridge. It sends
only the returned bearer to Seller Gateway; the original agent token is never forwarded downstream.

## Бесплатный доступ

`wildberries-agent-free` — техническая отметка бесплатного агентского доступа, а не платная
подписка. Seller Gateway должен получать её из доверенного подписанного bridge-токена (или
проверенного серверного introspection) и не требовать тариф, seat или оплату за вызов. Отметка
остаётся привязанной к текущему пользователю и поставщику и разрешает только восемь опубликованных
инструментов; запись ограничена описанным `cost_price:write` и не превращается в произвольный API-прокси.

Finance and price enrichment may remain unavailable in older Gateway deployments; the plugin
returns a warning instead of hiding the limitation. Once the entitlement is implemented for those
read routes, no plugin change is required.

## Supplier onboarding

The bridge and Seller service keep the existing ownership flow. `wb_connect_supplier` can open
`https://seller.bears.ru/authentication/registration` without an existing MCP bearer for a new
user, and opens `/wb-oauth/authorize` or the Seller integration page for an authenticated user.
The user enters the Wildberries personal token there. The MCP request, bridge response, logs, and
tool result must never contain that token. SMS/email and legal consent that Seller requires remain
inside the browser flow; the agent does not add a second confirmation screen.

## Failure behavior

- missing or invalid bridge configuration: fail closed with a stable error code;
- expired/rejected agent bearer: return an OAuth challenge or `identity_bridge_rejected`;
- bridge/upstream outage: return a generic availability error without provider response text;
- no raw token persistence in the bridge, gateway logs, MCP process, or repository.
