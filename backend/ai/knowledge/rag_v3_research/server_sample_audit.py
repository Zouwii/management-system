#!/usr/bin/env python3
"""Read-only structural audit for exported DingTalk Markdown files.

The script intentionally uses only the Python standard library so it can be
piped to the production server and run without installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+\S")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
LIST_RE = re.compile(r"^\s*(?:[-*+] |\d+[.)]\s+)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
HTML_RE = re.compile(r"</?[A-Za-z][^>]*>")


def profile(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    heading_levels: dict[str, int] = {}
    fenced_lines = 0
    in_fence = False
    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            level = str(len(match.group(1)))
            heading_levels[level] = heading_levels.get(level, 0) + 1
        if line.lstrip().startswith("```"):
            fenced_lines += 1
            in_fence = not in_fence

    relative = path.relative_to(root)
    return {
        "path": str(path),
        "relative_path": str(relative),
        "title": path.name,
        "bytes": path.stat().st_size,
        "chars": len(text),
        "lines": len(lines),
        "folder_depth": max(0, len(relative.parts) - 1),
        "headings": sum(heading_levels.values()),
        "heading_levels": heading_levels,
        "table_rows": sum(bool(TABLE_RE.match(line)) for line in lines),
        "list_lines": sum(bool(LIST_RE.match(line)) for line in lines),
        "fence_markers": fenced_lines,
        "images": len(IMAGE_RE.findall(text)),
        "html_tags": len(HTML_RE.findall(text)),
        "max_line_chars": max((len(line) for line in lines), default=0),
        "ends_in_open_fence": in_fence,
    }


def top(rows: list[dict], key: str, count: int, minimum: int = 1) -> list[dict]:
    eligible = [row for row in rows if int(row[key]) >= minimum]
    return sorted(eligible, key=lambda row: (row[key], row["chars"]), reverse=True)[:count]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/home/jz/zhr/markdown"))
    parser.add_argument("--top", type=int, default=12)
    args = parser.parse_args()

    paths = sorted(
        path for path in args.root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".adoc"}
    )
    rows = []
    errors = []
    for path in paths:
        try:
            rows.append(profile(path, args.root))
        except Exception as exc:  # keep one damaged export from aborting the audit
            errors.append({"path": str(path), "error": str(exc)})

    payload = {
        "root": str(args.root),
        "file_count": len(rows),
        "error_count": len(errors),
        "categories": {
            "deep_folder": top(rows, "folder_depth", args.top, minimum=4),
            "heading_rich": top(rows, "headings", args.top, minimum=5),
            "table_heavy": top(rows, "table_rows", args.top, minimum=4),
            "code_heavy": top(rows, "fence_markers", args.top, minimum=2),
            "image_heavy": top(rows, "images", args.top, minimum=1),
            "html_heavy": top(rows, "html_tags", args.top, minimum=1),
            "long_line": top(rows, "max_line_chars", args.top, minimum=1000),
        },
        "errors": errors[:50],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
