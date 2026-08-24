# Wildberries Agent Integration Instructions

## Product Contract

- Keep user-facing plugin, skill, tool, and directory descriptions in Russian.
- Use plain SemVer versions such as `1.2.3`; do not add build, channel, or prerelease suffixes.
- Keep all agent-facing Wildberries functionality in the free `wildberries-agent-free` entitlement.
- Treat Seller, including `apps/tokens-wb` in the canonical Seller repository, as the only store for Wildberries supplier credentials.
- Identify a connected supplier by the authenticated user and `supplier_id_wb`. Never accept, return, persist, or log a raw Wildberries token in MCP arguments, results, or plugin-owned storage.

## Integration Boundaries

- The public MCP is a thin authenticated client of Seller services; do not implement a second analytics backend, credential store, or arbitrary HTTP proxy in this repository.
- Allow the fixed reviewer sandbox only with public synthetic values.
- Keep the reviewer sandbox isolated from the identity bridge, Seller services, and databases.
- Never perform network calls from the reviewer sandbox.
- Expose only reviewed, bounded Seller and Wildberries operation identifiers. Models must not control upstream hosts, paths, methods, headers, or credentials.
- Keep source validation, public deployment, directory submission, and runtime acceptance as separate claims.
