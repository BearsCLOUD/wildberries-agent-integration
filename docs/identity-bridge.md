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

The bridge validates the agent token, maps its subject to the existing Seller user, checks that the
user is allowed to use the integration, and returns a short-lived Seller bearer:

```json
{
  "access_token": "<short-lived-seller-bearer>",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "analytics:read supplier:read supplier:connect",
  "entitlements": ["wildberries-agent-free"]
}
```

The plugin also accepts `seller_access_token` for compatibility with an existing bridge. It sends
only the returned bearer to Seller Gateway; the original agent token is never forwarded downstream.

## Free entitlement

`wildberries-agent-free` is a product entitlement, not a subscription bypass. Seller Gateway must
derive it from a trusted signed bridge token (or an authenticated server-side introspection result)
and grant all seven read/calculation tools without a plugin, seat, or per-call charge. The
entitlement must remain scoped to the authenticated Seller user and must not grant arbitrary API
proxy access or write permissions.

Finance and price enrichment may remain unavailable in older Gateway deployments; the plugin
returns a warning instead of hiding the limitation. Once the entitlement is implemented for those
read routes, no plugin change is required.

## Supplier onboarding

The bridge and Seller service keep the existing ownership flow. `wb_connect_supplier` opens
`/wb-oauth/authorize` when available, otherwise the authenticated Seller integration page. The user
enters the Wildberries personal token there. The MCP request, bridge response, logs, and tool result
must never contain that token.

## Failure behavior

- missing or invalid bridge configuration: fail closed with a stable error code;
- expired/rejected agent bearer: return an OAuth challenge or `identity_bridge_rejected`;
- bridge/upstream outage: return a generic availability error without provider response text;
- no raw token persistence in the bridge, gateway logs, MCP process, or repository.
