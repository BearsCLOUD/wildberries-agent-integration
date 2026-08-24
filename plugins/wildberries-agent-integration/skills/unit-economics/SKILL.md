---
name: unit-economics
description: Calculate Wildberries unit economics, margin, break-even price, and scenario deltas from explicit seller inputs. Use for calculator or profitability questions; do not invent fees or silently infer missing costs.
---

# Unit economics

Use the read-only `wb_unit_economics` calculator when available. Show the inputs, formula, result, and assumptions so the seller can reproduce the calculation.

## Inputs

Request or confirm: selling price, supplier cost, commission rate or amount, logistics, storage, fulfillment, advertising, tax, other per-unit costs, and the desired scenario (margin, break-even, or comparison). Accept a quantity or percentage only when its unit is clear.

At minimum, calculate:

`contribution = price - commission - logistics - storage - fulfillment - advertising - tax - other_costs - supplier_cost`

`margin_pct = contribution / price * 100` (when price is positive). For break-even, solve for the price under the supplied rates and state which costs are fixed or variable.

## Safety

- Do not present estimates as Wildberries billing facts or financial advice. Identify every assumed or user-supplied fee.
- Never fetch or expose supplier credentials. This skill is read-only and must not submit prices or discounts.
- If a required input is missing, ask for it or provide a clearly labeled range; never use a hidden default.

## Examples

**User:** “At 1,990 ₽, cost 700 ₽, commission 15%, logistics 180 ₽, and tax 6%, what is my margin?”

**Agent:** Show each deduction, contribution, margin percentage, and the assumptions about tax base and any omitted costs.

**User:** “What price gives me 20% margin?”

**Agent:** Ask for missing variable costs and solve the stated formula, showing whether commission and tax are modeled as percentages of price.
