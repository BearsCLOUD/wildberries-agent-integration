# Hosted MCP handoff

This compose file runs the Streamable HTTP server. Put it behind an HTTPS reverse proxy and an
OAuth 2.1/PKCE identity bridge before giving the URL to ChatGPT or Claude.

Required production variables:

- `SELLER_GATEWAY_URL=https://...`
- `SELLER_IDENTITY_BRIDGE_URL=https://...`
- `SELLER_CONNECT_URL=https://.../integration`
- `MCP_PUBLIC_URL=https://...`
- `MCP_AUTH_ISSUER=https://...`

The bridge receives the MCP bearer and `X-Identity-Audience: seller-gateway`, then returns a
short-lived Seller bearer for the signed-in user. It must enforce the free core-agent entitlement
and user/supplier ownership. Do not set `SELLER_ACCESS_TOKEN` in this deployment.

```bash
cp plugins/wildberries-agent-integration/.env.example plugins/wildberries-agent-integration/.env
# edit the values above, then:
docker compose -f deploy/docker-compose.yml up --build -d
curl -fsS https://your-host.example/healthz
curl -fsS https://your-host.example/.well-known/oauth-protected-resource/mcp
```

The repository does not claim a live host. DNS, TLS, OAuth registration, reviewer access, and
production secrets remain deployment-owned operations.
