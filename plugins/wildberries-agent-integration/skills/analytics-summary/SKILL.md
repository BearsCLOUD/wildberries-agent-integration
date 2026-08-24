---
name: analytics-summary
description: Summarize a seller's Wildberries sales, orders, returns, finance, prices, or stock for a stated period. Use when the user asks for analytics, a trend explanation, or a compact operational report; do not use for replenishment quantities or margin calculations.
---

# Analytics summary

Use the read-only `wb_analytics_summary` tool for the connected supplier. Keep the answer scoped to the authenticated user and name the supplier and reporting period.

## Inputs

- `supplier_id` or the user's unambiguous connected-supplier name;
- `from` and `to` dates (ask when the period is ambiguous);
- optional metric focus: sales, orders, returns, finance, prices, or stock;
- optional comparison period and requested detail level.

Report the source period, data freshness, headline metrics, material changes, and a short explanation of likely drivers. Separate observed values from interpretation and call out missing or partial data.

## Safety

- Never request, expose, or log a Wildberries token, cookie, bearer token, or raw provider error body.
- Do not imply that a dashboard read changed anything. Do not perform price, discount, or other writes from this skill.
- If the supplier is not connected or access is denied, explain the next safe action instead of guessing.

## Examples

**User:** “Show sales and returns for the last 14 days and explain the drop.”

**Agent:** Fetch the period, compare with the preceding 14 days when available, label the comparison, and list evidence-backed hypotheses with caveats.

**User:** “Give me a compact weekly report for supplier 123.”

**Agent:** Return a compact table with supplier, period, freshness, sales, orders, returns, and the most useful next action.
