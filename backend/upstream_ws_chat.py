#!/usr/bin/env python3
"""兼容入口：转发到 legacy 目录实现。"""

from ai.legacy.upstream_ws_chat import main


if __name__ == "__main__":
    raise SystemExit(main())
