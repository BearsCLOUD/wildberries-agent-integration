# Wildberries Agent Integration

Status: implementation brief derived from the operator request; the public-hosting values remain deployment configuration.

## Value proposition

Give Wildberries sellers a small set of agent-first actions inside Codex, Claude, and other MCP clients:

- connect a supplier through the existing Seller account flow;
- inspect sales, orders, returns, finance, prices, and stock;
- calculate unit economics and break-even scenarios;
- forecast how many units to replenish and which warehouse should receive them.

The agent tier is free: no plugin license, seat fee, or per-tool charge. A production identity
bridge must grant that entitlement for the core read routes. The plugin does not bypass Seller
subscription checks; optional finance and price enrichment remains entitlement-aware.

## Why an LLM

Natural-language requests such as “show the last 14 days and explain the drop” or “how many units should go to Kazan?” are faster than navigating several Seller screens. The LLM contributes intent parsing, comparisons, explanations, and a concise action plan. The Seller APIs remain the source of truth for user-scoped data and supplier permissions.

The plugin does not attempt to replace the Seller dashboard or expose a general-purpose arbitrary API proxy.

## Core actions

1. `wb_connect_supplier`: start a browser handoff to the existing secure onboarding flow. The Wildberries token is entered outside the prompt and is never returned to the agent.
2. `wb_analytics_summary` and `wb_warehouse_stock`: read user-scoped analytics and stock data through the Seller gateway.
3. `wb_unit_economics`: calculate margin, break-even price, commission, logistics, and scenario deltas from explicit inputs.
4. `wb_upload_cost_price`: записать явно указанную себестоимость одного товара в Seller.
5. `wb_inventory_forecast`: combine recent sales and stock data into a transparent replenishment recommendation by warehouse.

## UI overview

- First view: a short list of connected suppliers and three starter prompts (summary, calculator, replenishment forecast).
- Read actions: compact tables with source period, supplier, freshness, and assumptions.
- Calculator: inputs and formulas are shown next to the result.
- Forecast: recommended quantity, destination warehouse, coverage horizon, and uncertainty notes.
- End state: an answer that can be checked or copied into an operational plan; no silent write to Wildberries.

## Product context

- Canonical Seller source: `BearsCLOUD/seller`.
- Existing onboarding routes: authenticated `GET /wb-oauth/authorize` for an agent-safe browser handoff, or `POST /suppliers/create_supplier` followed by the existing WebSocket check flow. The service UI path is `Integration → Add supplier → Personal API token`.
- Existing read routes include `/suppliers`, `/statistics/report/combined`, and `/statistics/orders`.
  Finance (`/financial_report/dashboard/v2`) and price (`/price_management`) enrichment is optional
  and may be subscription-gated. Warehouse stock is an optional gateway adapter route; when it is
  unavailable, the forecast uses `deficit_districts` and labels the destination as a regional
  heuristic instead of inventing warehouse data.
- The MCP server uses the configured Seller gateway URL. In production/staging it exchanges the caller's MCP bearer at `SELLER_IDENTITY_BRIDGE_URL` and forwards only the short-lived Seller bearer; in local dev/test it may use a direct bearer or development-only static token. It never accepts a raw Wildberries token as a tool argument.
- Default transport is Streamable HTTP at `/mcp`. Local stdio is provided for development.
- Hosted deployments expose OAuth protected-resource metadata at `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp` when `MCP_PUBLIC_URL` and `MCP_AUTH_ISSUER` are configured.

## Authentication and safety

- Production HTTP deployments must use HTTPS and OAuth 2.1/PKCE or an equivalent short-lived user bearer flow.
- Production/staging deployments fail closed unless `SELLER_IDENTITY_BRIDGE_URL` is configured. The bridge validates the MCP audience and returns a short-lived Seller bearer; the agent bearer is never forwarded to Seller APIs.
- The implementation keeps the auth boundary explicit: authorization values are sent only in headers and are never logged.
- Supplier linking is an out-of-band browser action. A deployment can set `SELLER_CONNECT_URL` to the existing authenticated integration page.
- Read-only tools are the default. The only write in the first release is the scoped cost-price update; price and discount mutation remain out of scope.
- Responses contain no WB tokens, cookies, or provider-controlled error bodies.

## Non-goals for the first release

- no dashboard clone;
- no price or discount writes;
- no storage of user credentials in the plugin repository;
- no fake reviews, automated stars, or claims of guaranteed adoption;
- no hard-coded production hostnames or secrets.
