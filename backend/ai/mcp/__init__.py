"""MCP Server entry point.

Start via:
  python -m ai.mcp                    # stdio mode (single user, from env vars)
  python -m ai.mcp --transport sse    # SSE mode (multi-user, from query params)

stdio mode: set MCP_USER_ID / MCP_USER_NAME env vars for the single user.
SSE mode: clients connect with ?user_id=xxx&user_name=xxx in the URL.
"""

from __future__ import annotations

import argparse
import os
import sys


def _ensure_path():
    backend = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if backend not in sys.path:
        sys.path.insert(0, backend)


def main():
    _ensure_path()

    parser = argparse.ArgumentParser(description="TB MCP Server")
    parser.add_argument("--transport", choices=("stdio", "sse"), default="stdio")
    parser.add_argument("--port", type=int, default=5200, help="SSE listen port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="SSE listen host")
    args = parser.parse_args()

    if args.transport == "stdio":
        uid = os.getenv("MCP_USER_ID", "").strip()
        if not uid:
            print("[tb-mcp] WARNING: MCP_USER_ID not set. Tools requiring user context will fail.", file=sys.stderr)

    from ai.mcp.server import create_server, build_sse_app

    mcp = create_server()

    if args.transport == "sse":
        import uvicorn
        app = build_sse_app(mcp)
        print(f"[tb-mcp] SSE server starting on {args.host}:{args.port}", file=sys.stderr)
        uvicorn.run(app, host=args.host, port=args.port, forwarded_allow_ips="*")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
