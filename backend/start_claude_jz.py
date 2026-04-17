#!/usr/bin/env python3
"""
Python launcher for Claude CLI with custom gateway settings.

Usage:
  python start_claude_jz.py --api-key <sk-...>
  python start_claude_jz.py --api-key <sk-...> -- --help
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

DEFAULT_API_KEY = "sk-9NAw9y08AdKxYzRqYIvIGrgGugYBB0uPAkc4opBmf0pTmpW4"
DEFAULT_BASE_URL = "http://one-api.server22.jz"
DEFAULT_MODEL = "glm-5.1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start claude CLI with custom ANTHROPIC env vars.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ANTHROPIC_API_KEY", DEFAULT_API_KEY).strip(),
        help="Anthropic/OpenAI-compatible key (sk-...). If omitted, reads ANTHROPIC_API_KEY from environment.",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("ANTHROPIC_BASE_URL", DEFAULT_BASE_URL).strip(),
        help="Gateway base URL. Default: http://one-api.server22.jz",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL).strip(),
        help="Model name. Default: glm-5.1",
    )
    parser.add_argument(
        "claude_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed through to `claude` (use `--` before them).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.api_key:
        print("ERROR: missing api key. Provide --api-key or set ANTHROPIC_API_KEY.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = args.api_key
    env["ANTHROPIC_BASE_URL"] = args.base_url
    env["ANTHROPIC_MODEL"] = args.model

    passthrough = list(args.claude_args or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]

    cmd = ["claude", *passthrough]
    try:
        completed = subprocess.run(cmd, env=env)
        return int(completed.returncode)
    except FileNotFoundError:
        print("ERROR: `claude` command not found in PATH.", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())

