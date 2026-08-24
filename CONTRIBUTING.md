# Contributing

Keep changes small and agent-oriented. Add a focused tool or skill only when its inputs, output shape, permissions, and failure behavior are explicit.

## Versioning

Published plugin versions use plain SemVer only (for example, `0.1.3`). Keep the Codex manifest,
Claude manifest, and `pyproject.toml` on the same version. Do not append cachebuster, build, or
local metadata suffixes such as `+codex.20260824172754`.

```bash
cd plugins/wildberries-agent-integration
python3 -m pip install -e . pytest ruff
pytest -q
ruff check src tests
```

Use synthetic data in tests. Never include Wildberries tokens, Seller bearer values, cookies, or production payloads in commits, examples, or issue reports. Read-only tools are preferred; price, discount, and supplier mutations require a separate approval-gated design.
