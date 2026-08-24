# Public listing handoff

The repository is ready for a real catalog submission, but a public HTTPS host, OAuth identity bridge, support URL, privacy notice, terms, logo, and reviewer account still belong to deployment and publisher operations.

## OpenAI / ChatGPT

- Submit the canonical plugin directory: `plugins/wildberries-agent-integration`.
- Use the deployed Streamable HTTP URL, not the local `.mcp.json` command.
- Provide verified developer identity and reviewer credentials that do not require MFA or a private network.
- Include five positive and three negative tool-call cases.
- Verify the free agent-feature claim against the billing and listing metadata.

## Claude

- Validate the same directory with `claude plugin validate plugins/wildberries-agent-integration`.
- For Claude Connector, publish the HTTPS Streamable HTTP MCP endpoint.
- For Claude Desktop/Codex CLI, the bundled stdio config is suitable for local development.

## Launch message

> Free MCP integration for Wildberries sellers: connect a supplier, inspect sales and stock, calculate margin and break-even price, and forecast how much inventory to send to each warehouse.

Do not promise a precise future-sales guarantee. Do not automate stars, reviews, or account creation. Adoption should be organic and measurable from real users.
