# Security

## Credential handling

- Never pass a Wildberries token to an MCP tool.
- Enter personal tokens only in the authenticated Seller browser flow.
- Do not put bearer tokens in URLs, logs, traces, cache keys, issue reports, or screenshots.
- Production HTTP transport requires HTTPS and an OAuth 2.1/PKCE identity bridge.
- Production/staging requests require `SELLER_IDENTITY_BRIDGE_URL`; it exchanges the MCP bearer for a short-lived Seller bearer scoped to `seller-gateway`.
- The original MCP bearer is never forwarded to Seller APIs, persisted, or written to logs.
- `SELLER_ACCESS_TOKEN` is a development-only fallback and must not be set in public deployments.

## Data handling

The server forwards the caller's Seller bearer to the configured gateway and strips credential-like keys from tool results. Upstream error bodies are not returned to the agent. Keep provider data scoped to the requested supplier, period, and SKU set.

## Reporting

Report a vulnerability privately to the repository owner before opening a public issue. Include a minimal reproduction without credentials or seller data. Do not commit real tokens or production payloads.
