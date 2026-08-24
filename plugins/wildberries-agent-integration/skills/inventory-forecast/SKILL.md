---
name: inventory-forecast
description: Forecast Wildberries replenishment quantities and warehouse destinations from recent demand and current stock. Use for “how many units” or “where to ship” requests; do not use for arbitrary inventory writes.
---

# Inventory forecast

Use `wb_inventory_forecast` for the connected supplier. If the tool needs separate reads, combine `wb_analytics_summary` with `wb_warehouse_stock` and keep the recommendation traceable to both.

## Inputs

- supplier and SKU or product scope;
- forecast horizon and target coverage days;
- recent sales window (default only when the user accepts it);
- current stock, inbound stock, and warehouse split when available;
- optional service level, seasonality, or minimum shipment size.

Return recommended units by warehouse, coverage horizon, demand rate, stock used in the calculation, and uncertainty notes. A simple baseline is:

`recommended_units = max(0, demand_rate * coverage_days + safety_stock - available_stock - inbound_stock)`

State how demand rate and safety stock were chosen. If warehouse-level demand or stock is unavailable, say that the allocation is approximate and ask whether a fallback is acceptable.

## Safety

- This is a planning recommendation, not a guarantee of sales or delivery capacity. Flag sparse, stale, promotional, or anomalous data.
- Never silently allocate all stock to one warehouse or claim an operational shipment was created.
- Do not expose tokens or raw provider responses; do not perform inventory, price, or discount writes.

## Examples

**User:** “How many units of SKU A should go to Kazan for the next 21 days?”

**Agent:** Fetch demand and stock, show the baseline formula and assumptions, then return a rounded recommendation with uncertainty.

**User:** “We have 300 units inbound; where should they go?”

**Agent:** Compare warehouse demand and coverage, explain the split, and clearly label it as a plan for the seller to execute.
