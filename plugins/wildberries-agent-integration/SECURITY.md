# Security

## Credential handling

- Never pass a Wildberries token to an MCP tool.
- Enter personal tokens only in the authenticated Seller browser flow.
- Do not put bearer tokens in URLs, logs, traces, cache keys, issue reports, or screenshots.
- Production HTTP transport requires HTTPS and OAuth 2.1 with PKCE S256.
- Production/staging requests send the opaque MCP bearer only to fixed `/agent/...` routes on Seller Gateway.
- Seller Gateway validates the token resource, scope, linked Seller subject, and supplier ownership; it never exposes a Seller bearer to MCP.
- Hosted Streamable HTTP publishes protected-resource metadata and returns an OAuth bearer challenge before a protected request is handled.
- `SELLER_ACCESS_TOKEN` is a development-only fallback and must not be set in public deployments.

## Data handling

In production, the server forwards the caller's opaque MCP bearer only to fixed agent routes on the
configured Seller Gateway. In development, a configured static bearer may be used for local testing.
Credential-like keys are stripped from tool results. Upstream
error bodies are not returned to the agent. Keep provider data scoped to the requested supplier,
period, and SKU set.

## Reporting

Report a vulnerability privately to the repository owner before opening a public issue. Include a minimal reproduction without credentials or seller data. Do not commit real tokens or production payloads.
