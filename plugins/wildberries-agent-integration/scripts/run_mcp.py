#!/usr/bin/env python3
"""Run the bundled MCP server without requiring a global package install."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildberries_agent_mcp.__main__ import main  # noqa: E402


if __name__ == "__main__":
    main()
