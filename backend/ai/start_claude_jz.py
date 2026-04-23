#!/usr/bin/env python3
"""Start claude CLI with server22 gateway env vars."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_BASE_URL = "http://one-api.server22.jz"
DEFAULT_MODEL = "MiniMax-M2.7-highspeed"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
DEFAULT_CLAUDE_FLAGS = []


def _load_config(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def parse_args() -> argparse.Namespace:
    cfg = _load_config(DEFAULT_CONFIG_PATH)
    parser = argparse.ArgumentParser(
        description="Start claude CLI with custom ANTHROPIC env vars.",
    )
    parser.add_argument(
        "--api-key",
        default=str(os.getenv("ANTHROPIC_API_KEY", "")).strip() or str(cfg.get("api_key") or "").strip(),
        help="Gateway API key. If omitted, read ANTHROPIC_API_KEY from env.",
    )
    parser.add_argument(
        "--base-url",
        default=str(os.getenv("ANTHROPIC_BASE_URL", "")).strip()
        or str(cfg.get("base_url") or "").strip()
        or DEFAULT_BASE_URL,
        help=f"Gateway base URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--model",
        default=str(os.getenv("ANTHROPIC_MODEL", "")).strip()
        or str(cfg.get("model") or "").strip()
        or DEFAULT_MODEL,
        help=f"Model name. Default: {DEFAULT_MODEL}",
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

    cmd = ["claude", "--bare", *DEFAULT_CLAUDE_FLAGS, *passthrough]
    try:
        completed = subprocess.run(cmd, env=env)
        return int(completed.returncode)
    except FileNotFoundError:
        print("ERROR: `claude` command not found in PATH.", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())

