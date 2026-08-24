# Contributing

Keep changes small and agent-oriented. Add a focused tool or skill only when its inputs, output shape, permissions, and failure behavior are explicit.

```bash
cd plugins/wildberries-agent-integration
python3 -m pip install -e . pytest ruff
pytest -q
ruff check src tests
```

Use synthetic data in tests. Never include Wildberries tokens, Seller bearer values, cookies, or production payloads in commits, examples, or issue reports. Read-only tools are preferred; price, discount, and supplier mutations require a separate approval-gated design.
