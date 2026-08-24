from __future__ import annotations

import argparse
from dataclasses import replace

from .config import Settings
from .server import build_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Wildberries Agent Integration MCP server")
    parser.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.host is not None:
        settings = replace(settings, host=args.host)
    if args.port is not None:
        settings = replace(settings, port=args.port)
    build_server(settings).run(transport=args.transport)


if __name__ == "__main__":
    main()
