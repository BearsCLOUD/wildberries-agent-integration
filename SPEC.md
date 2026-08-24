# Wildberries Agent Integration

Status: implementation brief derived from the operator request; the public-hosting values remain deployment configuration.

## Value proposition

Give Wildberries sellers a small set of agent-first actions inside Codex, Claude, and other MCP clients:

- connect a supplier through the existing Seller account flow;
- inspect sales, orders, returns, finance, prices, and stock;
- compare explicit competitor observations and calculate a robust price corridor;
- aggregate supplied sales rows by their actual region field and product identifier;
- test a weather-and-sales hypothesis on aligned observations without claiming causation;
- score product-card content completeness for explicit SEO keywords;
- create product-card drafts, reusable design-system rules, and product-photo prompts through skills;
- calculate unit economics and break-even scenarios;
- forecast how many units to replenish and which warehouse should receive them.

The agent tier is free: no plugin license, seat fee, or per-tool charge. A production identity
bridge must grant that entitlement for the core read routes. The plugin does not bypass Seller
subscription checks; optional finance and price enrichment remains entitlement-aware.

## Why an LLM

Natural-language requests such as “show the last 14 days and explain the drop” or “how many units should go to Kazan?” are faster than navigating several Seller screens. The LLM contributes intent parsing, comparisons, explanations, and a concise action plan. The Seller APIs remain the source of truth for user-scoped data and supplier permissions.

The plugin does not attempt to replace the Seller dashboard or expose a general-purpose arbitrary API proxy.

Russian discovery positioning should use natural phrases such as «аналитика Wildberries»,
«анализ конкурентов Wildberries», «сравнение цен», «продажи по регионам»,
«погода и продажи», «SEO карточки Wildberries», «юнит-экономика» and «прогноз
пополнения». Listing copy must not imply access to competitor private metrics, guaranteed
rankings, exact demand, or causal attribution.

## Core actions

1. `wb_connect_supplier`: start a browser handoff to the existing secure onboarding flow. The Wildberries token is entered outside the prompt and is never returned to the agent.
2. `wb_analytics_summary` and `wb_warehouse_stock`: read user-scoped analytics and stock data through the Seller gateway.
3. `wb_wildberries_proxy`: call one fixed, read-only Seller Gateway operation. The model cannot supply a token, host, URL, path, HTTP method, or headers.
4. `wb_competitor_analysis`: summarize a caller-supplied, comparable competitor sample inside an authenticated supplier scope. No sample means `source_required`, not an invented conclusion.
5. `wb_competitive_price`: calculate the sample's quartile price corridor and seller position; optional cost inputs are constraints, not a complete profitability model.
6. `wb_sales_by_region`: aggregate explicit rows or, for an authenticated supplier and `nm_id`, read the fixed `/statistics/tape/v2` source and filter the requested period locally. It must not infer buyer region from a warehouse or logistics hub.
7. `wb_sales_weather_impact`: join supplied sales and weather rows by compatible date and region and report an observed correlation with sample-size and confounder caveats.
8. `wb_seo_analytics`: calculate a deterministic content-completeness heuristic for the supplied title, description, keywords, characteristics, and optional competitor-title benchmark. It is not a Wildberries ranking model.
9. `wb_unit_economics`: calculate margin, break-even price, commission, logistics, and scenario deltas from explicit inputs.
10. `wb_upload_cost_price`: write the explicitly supplied cost price for one product to Seller.
11. `wb_inventory_forecast`: combine recent sales and stock data into a transparent replenishment recommendation by warehouse.

The five new analysis tools are bounded, read-only, idempotent operations. They accept structured
data and documented identifiers, not an upstream URL, path, method, header, cookie, bearer, or raw Wildberries token. Their
tool annotations are `readOnlyHint=true`, `destructiveHint=false`, `idempotentHint=true`, and
`openWorldHint=false`.

The card, design-system, and photo-generation capabilities are skill workflows rather than hidden
provider writes. They produce drafts or imagegen prompts, preserve confirmed product facts, and do
not publish or mutate a Wildberries card without a separate explicit user action.

## UI overview

- First view: a short list of connected suppliers and three starter prompts (summary, calculator, replenishment forecast).
- Read actions: compact tables with source period, supplier, freshness, and assumptions.
- Calculator: inputs and formulas are shown next to the result.
- Forecast: recommended quantity, destination warehouse, coverage horizon, and uncertainty notes.
- Advanced analysis: compact source counts, excluded or skipped rows, calculation method, and a
  caveat that separates observed facts from a scenario or hypothesis.
- End state: an answer that can be checked or copied into an operational plan; no silent write to Wildberries.

## Evidence and interpretation contract

- Seller data is authoritative only for the authenticated user's permitted supplier and for the
  fields, period, and freshness returned by the Seller route.
- Competitor rows and prices describe only the explicit sample. A public card snapshot does not
  reveal competitor sales, conversion, advertising spend, stock history, or unit economics.
- Regional aggregation uses the geographic field present in each row. Warehouse, district, buyer
  region, and stock location remain different dimensions unless the source explicitly equates them.
- Weather output is correlation context. It does not establish that weather caused a sales change;
  seasonality, promotions, price, stock, region mix, and other confounders may explain it.
- The SEO score is a transparent content-completeness heuristic. It does not observe the
  Wildberries ranking algorithm, query frequency, impressions, CTR, conversion, or future position.
- Missing or malformed evidence remains missing or excluded. It is never replaced by generated
  competitor facts, zero-filled weather, inferred geography, or fabricated marketplace metrics.

## Product context

- Canonical Seller source: `BearsCLOUD/seller`.
- Existing onboarding routes: authenticated `GET /wb-oauth/authorize` for an agent-safe browser handoff, or `POST /suppliers/create_supplier` followed by the existing WebSocket check flow. The service UI path is `Integration → Add supplier → Personal API token`.
- Existing read routes include `/suppliers`, `/statistics/report/combined`, and `/statistics/orders`.
  Finance (`/financial_report/dashboard/v2`) and price (`/price_management`) enrichment is optional
  and may be subscription-gated. Warehouse stock is an optional gateway adapter route; when it is
  unavailable, the forecast uses `deficit_districts` and labels the destination as a regional
  heuristic instead of inventing warehouse data.
- Product-by-region live enrichment uses only `/statistics/tape/v2` with authenticated
  `supplier_id_wb`, required `nm_id`, bounded paging, and local period filtering.
  `/statistics/report/combined` has no region field and is not a regional-sales source.
- The MCP server uses the configured Seller gateway URL. In production/staging it exchanges the caller's MCP bearer at `SELLER_IDENTITY_BRIDGE_URL` and forwards only the short-lived Seller bearer; in local dev/test it may use a direct bearer or development-only static token. It never accepts a raw Wildberries token as a tool argument.
- Default transport is Streamable HTTP at `/mcp`. Local stdio is provided for development.
- Hosted deployments expose OAuth protected-resource metadata at `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp` when `MCP_PUBLIC_URL` and `MCP_AUTH_ISSUER` are configured.
- The public MCP is deployed beside the analytics server. `seller.bears.ru` remains the browser
  registration, sign-in, and supplier-connection surface; it is not presented as the analytics MCP host.

### Proxy ownership boundary

`wb_wildberries_proxy` is a public MCP tool with a fixed read-only Seller Gateway contract, not an
arbitrary upstream proxy. Its MCP arguments are `supplier_id_wb`, an allowlisted `operation`, and a
bounded operation-specific `payload`. It must not accept a raw token, upstream URL, HTTP method,
arbitrary path, headers, or arbitrary provider body. Seller Gateway owns authentication, supplier
ownership checks, operation allowlisting, and resolution of the stored Wildberries credential.
Live availability depends on the deployed Seller Gateway configuration; repository support does
not prove that any production host currently accepts an operation, and no production hostname is
hard-coded or claimed here.

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
- no public arbitrary proxy or caller-controlled upstream request;
- no inferred competitor sales, query frequency, buyer region, or weather causality;
- no promise that a price, SEO edit, regional allocation, or weather scenario will increase sales;
- no storage of user credentials in the plugin repository;
- no fake reviews, automated stars, or claims of guaranteed adoption;
- no hard-coded production hostnames or secrets.
