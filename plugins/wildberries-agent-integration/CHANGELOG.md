# Changelog

## 0.1.10

- Added the exact OpenAI domain-verification challenge route for a production deployment.
- Added bounded review and rating reads through the existing Seller Gateway plus a Russian review-analysis skill.
- Added a Russian skill for capability-driven read-only Wildberries Seller API operations.
- Added a Russian OpenAI Plugins Directory submission pack, reviewer scenarios, and listing copy.
- Reworked the repository presentation around free agent analytics, replenishment, and secure Seller ownership.

## 0.1.9

- Added Russian skills for competitor analysis, competitive pricing, regional sales, weather impact,
  SEO analytics, product-card creation, design systems, and product-photo generation.
- Added bounded read-only MCP tools for competitor context, price corridors, regional sales, weather
  hypotheses, SEO completeness, and fixed Seller Gateway operations.
- Kept provider credentials server-side and standardized all public package versions on plain SemVer.

## 0.1.8

- Removed the extra confirmation round-trip from `wb_upload_cost_price`; explicit tool arguments now execute immediately within Seller ownership.

## 0.1.7

- Made `wb_connect_supplier` open new-user registration at `seller.bears.ru` without an MCP bearer or extra confirmation.
- Documented the analytics server as the public MCP host; Seller remains the browser onboarding service.

## 0.1.6

- Made cost-price writes return a canonical status only after Seller echoes the requested `nm_id` and amount.
- Added an explicit unknown-write outcome for empty, mismatched, timeout, or server-error responses.

## 0.1.5

- Added focused tests proving cost-price confirmation, bearer fail-closed behavior, and payload redaction.

## 0.1.4

- Added `wb_upload_cost_price`, a confirmation-gated tool for writing one product cost price to Seller.
- Added the Russian `cost-price-upload` skill with explicit confirmation guidance.

## 0.1.3

- Added a dedicated replenishment calculator skill for fast, transparent quantity planning.
- Localized catalog descriptions, MCP tool metadata, skills, and public README to Russian.
- Standardized published manifests on plain SemVer without build or cachebuster suffixes.

## 0.1.2

- Added a Claude-specific MCP config using `${CLAUDE_PLUGIN_ROOT}` while keeping Codex's local config separate.
- Published the identity-bridge and free-entitlement contract for hosted deployments.

## 0.1.1

- Added fail-closed HTTPS and handoff URL validation.
- Made optional finance/price enrichment non-blocking for the free core analytics flow.
- Added regional-demand allocation when warehouse stock is not exposed by the gateway.
- Corrected MCP tool annotations and protected-resource metadata validation.

## 0.1.0

- Added Codex and Claude plugin manifests.
- Added Streamable HTTP and local stdio MCP transports.
- Added supplier handoff, analytics summary, warehouse stock, unit economics, replenishment math, and inventory forecast tools.
- Added four concise agent skills and security guidance.
