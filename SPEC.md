# Wildberries Agent Integration

Status: implementation brief derived from the operator request; the public-hosting values remain deployment configuration.

## Value proposition

Give Wildberries sellers a small set of agent-first actions inside Codex, Claude, and other MCP clients:

- connect a supplier through the existing Seller account flow;
- inspect sales, orders, returns, finance, prices, and stock;
- calculate unit economics and break-even scenarios;
- forecast how many units to replenish and which warehouse should receive them.

The agent tier is free. Wildberries fees, Seller service limits, and infrastructure costs are separate from the plugin.

## Why an LLM

Natural-language requests such as “show the last 14 days and explain the drop” or “how many units should go to Kazan?” are faster than navigating several Seller screens. The LLM contributes intent parsing, comparisons, explanations, and a concise action plan. The Seller APIs remain the source of truth for user-scoped data and supplier permissions.

The plugin does not attempt to replace the Seller dashboard or expose a general-purpose arbitrary API proxy.

## Core actions

1. `wb_connect_supplier`: start a browser handoff to the existing secure onboarding flow. The Wildberries token is entered outside the prompt and is never returned to the agent.
2. `wb_analytics_summary` and `wb_warehouse_stock`: read user-scoped analytics and stock data through the Seller gateway.
3. `wb_unit_economics`: calculate margin, break-even price, commission, logistics, and scenario deltas from explicit inputs.
4. `wb_inventory_forecast`: combine recent sales and stock data into a transparent replenishment recommendation by warehouse.

## UI overview

- First view: a short list of connected suppliers and three starter prompts (summary, calculator, replenishment forecast).
- Read actions: compact tables with source period, supplier, freshness, and assumptions.
- Calculator: inputs and formulas are shown next to the result.
- Forecast: recommended quantity, destination warehouse, coverage horizon, and uncertainty notes.
- End state: an answer that can be checked or copied into an operational plan; no silent write to Wildberries.

## Product context

- Canonical Seller source: `BearsCLOUD/seller`.
- Existing onboarding routes: authenticated `GET /wb-oauth/authorize` for an agent-safe browser handoff, or `POST /suppliers/create_supplier` followed by the existing WebSocket check flow. The service UI path is `Integration → Add supplier → Personal API token`.
- Existing read routes include `/suppliers`, `/statistics/report/combined`, `/financial_report/v2`, `/price_management`, and `/price_management/stocks-report/wb-warehouses`.
- The MCP server uses the configured Seller gateway URL and forwards the caller's user bearer token; it never accepts a raw Wildberries token as a tool argument.
- Default transport is Streamable HTTP at `/mcp`. Local stdio is provided for development.

## Authentication and safety

- Production HTTP deployments must use HTTPS and OAuth 2.1/PKCE or an equivalent short-lived user bearer flow.
- The implementation keeps the auth boundary explicit: `Authorization` is forwarded only to the configured Seller gateway and is never logged.
- Supplier linking is an out-of-band browser action. A deployment can set `SELLER_CONNECT_URL` to the existing authenticated integration page.
- Read-only tools are the default. Price/discount mutation is intentionally out of scope for the first release.
- Responses contain no WB tokens, cookies, or provider-controlled error bodies.

## Non-goals for the first release

- no dashboard clone;
- no price or discount writes;
- no storage of user credentials in the plugin repository;
- no fake reviews, automated stars, or claims of guaranteed adoption;
- no hard-coded production hostnames or secrets.
