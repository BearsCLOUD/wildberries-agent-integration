# MCP contract examples

The server exposes Streamable HTTP at `/mcp` in a deployment. Local stdio uses the same tool names.

## Calculator

`wb_unit_economics` has no Seller credentials and is safe to run on synthetic data:

```json
{
  "price": 1990,
  "cost_price": 620,
  "commission_percent": 18,
  "logistics_per_unit": 120,
  "storage_per_unit": 14,
  "advertising_per_unit": 80,
  "tax_percent": 6,
  "discount_percent": 10,
  "target_margin_percent": 25
}
```

The result includes `net_price`, `profit`, `margin_percent`, `break_even_price`, `target_margin_price`, and the assumptions used.

## Forecast

`wb_inventory_forecast` accepts a supplier ID and optional `nm_ids`, then reads the Seller deficit and warehouse stock routes. The response includes `recommended_qty`, `destinations`, `district_demand`, `warehouse_stock_status`, and warnings when warehouse-level demand is unavailable.

## Error shape

Tools return a small stable object:

```json
{
  "ok": false,
  "error": {"code": "auth_required"}
}
```

Provider response bodies and credentials are intentionally omitted from errors.
