# Changelog

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
