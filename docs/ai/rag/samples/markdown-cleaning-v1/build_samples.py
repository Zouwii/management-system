"""Regenerate the cleaned Markdown comparison fixtures."""

from __future__ import annotations

import json
import sys
from difflib import unified_diff
from pathlib import Path


SAMPLE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SAMPLE_DIR.parents[4] / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.knowledge.v2.cleaner import clean_markdown  # noqa: E402


def main() -> None:
    original_dir = SAMPLE_DIR / "original"
    cleaned_dir = SAMPLE_DIR / "cleaned"
    diff_dir = SAMPLE_DIR / "diff"
    cleaned_dir.mkdir(exist_ok=True)
    diff_dir.mkdir(exist_ok=True)
    comparison = []

    for source in sorted(original_dir.glob("*.md")):
        raw = source.read_text(encoding="utf-8")
        result = clean_markdown(raw, source.stem)
        second_pass = clean_markdown(result.cleaned_md, source.stem)
        if second_pass.cleaned_md != result.cleaned_md:
            raise RuntimeError(f"cleaning is not idempotent: {source.name}")
        if result.cleaned_md.count("【图片") != result.stats["image_count"]:
            raise RuntimeError(f"image placeholder count changed: {source.name}")
        if len(result.deprecated_blocks) != result.stats["deprecated_count"]:
            raise RuntimeError(f"deprecated content count changed: {source.name}")
        target = cleaned_dir / source.name
        cleaned_text = result.cleaned_md + "\n"
        target.write_text(cleaned_text, encoding="utf-8")
        diff_text = "".join(
            unified_diff(
                raw.splitlines(keepends=True),
                cleaned_text.splitlines(keepends=True),
                fromfile=f"original/{source.name}",
                tofile=f"cleaned/{source.name}",
            )
        )
        (diff_dir / f"{source.stem}.diff").write_text(
            diff_text, encoding="utf-8"
        )
        comparison.append(
            {
                "file": source.name,
                **result.stats,
                "reduction_chars": result.stats["input_chars"]
                - result.stats["output_chars"],
                "reduction_percent": round(
                    100
                    * (
                        result.stats["input_chars"]
                        - result.stats["output_chars"]
                    )
                    / max(result.stats["input_chars"], 1),
                    2,
                ),
                "warnings": result.warnings,
            }
        )

    (SAMPLE_DIR / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
