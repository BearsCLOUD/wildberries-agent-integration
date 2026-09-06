# Agent identity boundary

The plugin intentionally has no user database, Seller session store, or Wildberries-token store.
Seller Gateway owns OAuth 2.1 with DCR and PKCE S256 at `https://passport.bears.ru`.

## Agent bearer

The MCP server forwards the caller's opaque bearer only in the `Authorization` header to fixed
`/agent/...` routes on Seller Gateway. It never exchanges that bearer for, accepts, or returns a
Seller bearer. Agent access records contain the agent subject, exact MCP resource, scopes, and a
bounded TTL; they contain neither a Seller bearer nor a Wildberries credential.

Before each protected operation, Seller Gateway validates:

- the opaque agent token and exact resource `https://wb.seller.bears.ru/mcp`;
- scope `wildberries-agent-free`;
- the optional link from the agent subject to an active Seller subject;
- ownership of the requested `supplier_id_wb`;
- that the requested route and operation are on the fixed agent allowlist.

The agent surface is free for every connected Seller user. Ordinary non-agent Seller routes retain
their existing subscription rules.

## Seller linking

A new OAuth client can receive an anonymous agent token before a Seller account is linked.
`wb_connect_supplier`, `wb_connection_status`, and `wb_connect_telegram` then return a safe browser
or Telegram next step. A one-time link code is carried in the browser URL fragment, consumed after
Seller login or registration, and never appears in server request logs. The user enters the
Wildberries personal token only in Seller. MCP arguments, results, and storage never contain it.

## Reviewer sandbox

The reviewer contour uses the public synthetic token `wb-agent-sandbox-token-v1` and supplier
`900000001`. It is fully virtual: no Seller Gateway, database, or Wildberries request is made and no
external state is changed, including the confirmed cost-price example.

## Failure behavior

- missing or invalid bearer: return an OAuth challenge with the protected-resource metadata URL;
- unlinked Seller identity: return a safe linking next step without Seller data;
- unavailable Gateway: return a generic availability error without provider response text;
- revoked or inactive Seller account: deny the operation;
- never persist or log authorization headers, Seller sessions, Wildberries tokens, or provider
  response bodies.
