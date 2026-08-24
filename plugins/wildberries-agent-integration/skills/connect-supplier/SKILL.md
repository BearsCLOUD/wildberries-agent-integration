---
name: connect-supplier
description: Help a seller connect a Wildberries supplier through the existing secure Seller onboarding flow. Use when the user asks to add, link, or authorize a supplier; never collect a raw Wildberries token in chat.
---

# Connect supplier

Use `wb_connect_supplier` to start the configured browser handoff to the Seller service. The user enters the Wildberries personal API token on the authenticated Seller page, outside the agent conversation. The tool may return a short-lived handoff URL or status, but never a token.

## Inputs

- an optional supplier label or the user's requested account name;
- confirmation that the user wants to open the Seller onboarding flow;
- if the service asks for it, the user's authenticated Seller session.

After the handoff, tell the user to complete `Integration → Add supplier → Personal API token` and return to the agent to check connection status. Do not claim success until the service reports the supplier as connected.

## Safety

- Never ask the user to paste a Wildberries token, cookie, or bearer token into chat or a tool argument.
- Never log, echo, persist, or inspect credential values. Do not include them in examples, URLs, or error reports.
- Treat the handoff URL as sensitive and short-lived; show only the minimum needed to open it.
- If the flow fails, report a generic next step and safe status; do not relay provider-controlled response bodies.

## Examples

**User:** “Connect my Wildberries supplier.”

**Agent:** Start the secure handoff, explain where to enter the token, and wait for the service's connection status.

**User:** “Here is my WB token: …”

**Agent:** Do not process or repeat it; tell the user to revoke or rotate an exposed token and use the secure Seller page instead.
