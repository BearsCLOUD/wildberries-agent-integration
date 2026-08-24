# Wildberries Agent Integration

[![CI](https://github.com/BearsCLOUD/wildberries-agent-integration/actions/workflows/ci.yml/badge.svg)](https://github.com/BearsCLOUD/wildberries-agent-integration/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/BearsCLOUD/wildberries-agent-integration)](https://github.com/BearsCLOUD/wildberries-agent-integration/releases)
[![Stars](https://img.shields.io/github/stars/BearsCLOUD/wildberries-agent-integration)](https://github.com/BearsCLOUD/wildberries-agent-integration)

Free MCP tools for Wildberries sellers who work in Codex, Claude, or another MCP-compatible agent.

Move from a question to a checked number and an operational next step:

- read sales, orders, finance, prices, and stock through the Seller account;
- calculate commission, logistics, tax, margin, and break-even price;
- forecast replenishment and show how the recommendation is split across warehouses or regions;
- start supplier onboarding through the existing Seller browser flow.

The agent tier is intended to be free: this plugin has no license fee, seat fee, or tool metering.
The production identity bridge must grant the free agent entitlement for the core read routes;
the adapter never bypasses Seller billing or access controls. Wildberries fees and infrastructure
costs remain separate.

## Security boundary

The MCP server exchanges the authenticated agent bearer through `SELLER_IDENTITY_BRIDGE_URL` in
production; the bridge must return a short-lived Seller bearer scoped to the current user. Only that
short-lived bearer is sent to the configured gateway. When available the server starts the existing
`GET /wb-oauth/authorize` flow; otherwise it opens the Seller integration page. A raw Wildberries
token is never a tool argument, URL parameter, log field, repository file, or MCP result. Supplier
tokens are entered only in the existing browser flow:

`Integration → Add supplier → Personal API token`

The first release is read-first: it does not change prices, discounts, or supplier settings.

## Tools

| Tool | Purpose | Auth |
| --- | --- | --- |
| `wb_connect_supplier` | Open the secure Seller onboarding handoff | Browser flow |
| `wb_list_suppliers` | List the current user's connected suppliers | Seller bearer |
| `wb_analytics_summary` | Sales/orders with optional finance and price data | Seller bearer |
| `wb_warehouse_stock` | Current WB warehouse stock by `nm_id` | Seller bearer |
| `wb_unit_economics` | Margin and break-even calculator | None |
| `wb_replenishment_math` | Deterministic stock quantity calculator | None |
| `wb_inventory_forecast` | Deficit + stock based replenishment recommendation | Seller bearer |

Forecasts return the period, formula, destination allocation, data status, and warnings. They are recommendations, not guarantees of future demand.

## Local development

```bash
cd plugins/wildberries-agent-integration
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
export SELLER_GATEWAY_URL=http://127.0.0.1:8000
export SELLER_CONNECT_URL=https://seller.example.com/integration
wildberries-agent-mcp
```

For a local MCP client, use the bundled `.mcp.json`. For an HTTP server:

```bash
wildberries-agent-mcp --transport streamable-http --host 0.0.0.0 --port 8080
```

Production deployments must put the server behind HTTPS and an OAuth 2.1/PKCE identity bridge. Set
`SELLER_IDENTITY_BRIDGE_URL` to the service-to-service exchange endpoint; without it,
production/staging calls fail closed. Set `MCP_PUBLIC_URL` and `MCP_AUTH_ISSUER` to publish
protected-resource metadata for ChatGPT/Claude connectors. The public URL is deployment-specific
and is intentionally not hard-coded in this repository.

Core statistics, supplier listing, calculators, and the deficit forecast are the free agent
surface. Finance and price-table enrichment are opt-in and return a clear warning when the current
Seller entitlement does not include them. Warehouse stock is optional: if the gateway route is not
published yet, the forecast falls back to regional demand and labels the destination as a heuristic.

## Codex and Claude

The canonical plugin source is `plugins/wildberries-agent-integration` and contains both `.codex-plugin/plugin.json` and `.claude-plugin/plugin.json`.

Codex uses the repository marketplace entry at `.agents/plugins/marketplace.json` (`wildberries-agent`). Claude can load the plugin directory directly or connect to the deployed Streamable HTTP endpoint. See [docs/public-listing.md](docs/public-listing.md) before submitting to a public catalog.

## Source mapping

The adapter uses the existing Seller gateway routes rather than exposing internal services directly:

- `/suppliers`
- `/statistics/report/combined`
- `/statistics/orders`
- `/financial_report/dashboard/v2` (optional entitlement)
- `/price_management` (optional entitlement)
- `/price_management/stocks-report/wb-warehouses` (optional gateway adapter; forecast has a regional fallback)

See [SPEC.md](SPEC.md) for the bounded product contract and [docs/mcp-contract.md](docs/mcp-contract.md) for request and response examples.
The exact identity and free-entitlement handoff is in [docs/identity-bridge.md](docs/identity-bridge.md).

Hosted operators should publish the deployment-specific [privacy notice](plugins/wildberries-agent-integration/PRIVACY.md),
[terms](plugins/wildberries-agent-integration/TERMS.md), and [support path](plugins/wildberries-agent-integration/SUPPORT.md)
before catalog submission.

## License

MIT. See [LICENSE](LICENSE).
