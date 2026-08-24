# Public listing handoff

The repository is ready for a catalog handoff, but it is not a hosted listing by itself. A public
HTTPS host, OAuth identity bridge, support URL, deployment-specific privacy/terms notice, logo, and
reviewer account still belong to deployment and publisher operations.

## OpenAI / ChatGPT

- Submit the canonical plugin directory: `plugins/wildberries-agent-integration`.
- Use the deployed Streamable HTTP URL, not the local `.mcp.json` command.
- Provide verified developer identity and reviewer credentials that do not require MFA or a private network.
- Include five positive and three negative tool-call cases.
- Verify the free agent-feature claim against the billing and listing metadata. The bridge must
  grant the free core-agent entitlement; this repository must not be used to bypass a paid Seller
  route.
- Attach the [identity bridge contract](identity-bridge.md) and document the free entitlement for
  reviewers.

## Claude

- Validate the same directory with `claude plugin validate plugins/wildberries-agent-integration`.
- For Claude Connector, publish the HTTPS Streamable HTTP MCP endpoint.
- For Claude Desktop/Codex CLI, the bundled stdio config is suitable for local development.

## Launch message

> Free MCP integration for Wildberries sellers: connect a supplier, inspect sales and stock, calculate margin and break-even price, and forecast how much inventory to send to each warehouse.

Do not promise a precise future-sales guarantee. Do not automate stars, reviews, or account creation. Adoption should be organic and measurable from real users.

## Review cases

Use these cases with a reviewer account after the public host and identity bridge are live.

Positive:

1. `wb_unit_economics` with explicit price, cost, commission, logistics, and tax returns a
   reproducible margin and break-even formula.
2. `wb_replenishment_math` with daily sales, stock, target days, safety days, and inbound units
   returns a non-negative whole-unit recommendation.
3. `wb_connect_supplier` returns an HTTPS Seller handoff and never asks for a token in chat.
4. `wb_analytics_summary` returns a bounded period for a supplier owned by the signed-in user.
5. `wb_inventory_forecast` returns recommended units, destination type, assumptions, and warnings.

Negative:

1. A tool call without a user bearer returns `auth_required` (or the host's OAuth challenge), not
   supplier data.
2. A production server without `SELLER_IDENTITY_BRIDGE_URL` returns
   `identity_bridge_not_configured` and does not call Seller.
3. A handoff URL containing a token-like query parameter is rejected as `unsafe_connect_url`.
