#!/usr/bin/env python3
"""Compatibility entrypoint for ai.start_claude_jz."""

from ai.start_claude_jz import main


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Backward-compatible entrypoint for relocated Claude launcher."""

from ai.scripts.start_claude_jz import main


if __name__ == "__main__":
    raise SystemExit(main())

