#!/usr/bin/env python3
"""Run the current Cleaner → outline → Chunker pipeline on v3 samples."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from transformers import AutoTokenizer

from ai.knowledge.chunker import chunk_document, classify_document, count_tokens
from ai.knowledge.cleaner import clean_markdown
from ai.knowledge.routes import _extract_outline_v2


TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.:/+-]*|[0-9]+(?:\.[0-9]+)*|[\u4e00-\u9fff]")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+\S")
TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
HTML_RE = re.compile(r"</?[A-Za-z][^>]*>")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def lexical_recall(source: str, candidate: str) -> float:
    source_tokens = Counter(TOKEN_RE.findall(source))
    candidate_tokens = Counter(TOKEN_RE.findall(candidate))
    total = sum(source_tokens.values())
    if not total:
        return 1.0
    kept = sum(min(count, candidate_tokens[token]) for token, count in source_tokens.items())
    return kept / total


def structural_stats(text: str) -> dict:
    lines = text.splitlines()
    return {
        "chars": len(text),
        "lines": len(lines),
        "headings": sum(bool(HEADING_RE.match(line)) for line in lines),
        "table_rows": sum(bool(TABLE_RE.match(line)) for line in lines),
        "fence_markers": sum(line.lstrip().startswith("```") for line in lines),
        "images": len(IMAGE_RE.findall(text)),
        "html_tags": len(HTML_RE.findall(text)),
        "max_line_chars": max((len(line) for line in lines), default=0),
    }


def walk_jsonml(node: Any, depth: int = 0) -> Iterable[tuple[str, dict, int]]:
    if not isinstance(node, list) or not node or not isinstance(node[0], str):
        return
    tag = node[0]
    attrs = node[1] if len(node) > 1 and isinstance(node[1], dict) else {}
    yield tag, attrs, depth
    child_start = 2 if attrs else 1
    for child in node[child_start:]:
        yield from walk_jsonml(child, depth + 1)


def native_stats(native_dir: Path, slug: str) -> dict:
    markdown_payload = json.loads((native_dir / f"{slug}.markdown.json").read_text(encoding="utf-8"))
    blocks_payload = json.loads((native_dir / f"{slug}.blocks.json").read_text(encoding="utf-8"))
    jsonml_payload = json.loads((native_dir / f"{slug}.jsonml.json").read_text(encoding="utf-8"))
    outline_payload = json.loads((native_dir / f"{slug}.outline.json").read_text(encoding="utf-8"))

    native_markdown = str(markdown_payload.get("markdown") or "")
    blocks = blocks_payload.get("blocks") or []
    block_types = Counter(str(block.get("blockType") or "unknown") for block in blocks)

    jsonml_raw = jsonml_payload.get("jsonml")
    jsonml_tags: Counter[str] = Counter()
    jsonml_max_depth = 0
    jsonml_error = str(jsonml_payload.get("errorMsg") or "")
    if isinstance(jsonml_raw, str) and jsonml_raw.strip():
        try:
            parsed = json.loads(jsonml_raw)
            walked = list(walk_jsonml(parsed))
            jsonml_tags.update(tag for tag, _attrs, _depth in walked)
            jsonml_max_depth = max((depth for _tag, _attrs, depth in walked), default=0)
        except json.JSONDecodeError as exc:
            jsonml_error = str(exc)

    native_outline_raw = outline_payload.get("jsonml")
    native_outline_count = 0
    if isinstance(native_outline_raw, str) and native_outline_raw.strip():
        try:
            parsed_outline = json.loads(native_outline_raw)
            native_outline_count = sum(
                tag in {"h1", "h2", "h3", "h4", "h5", "h6"}
                for tag, _attrs, _depth in walk_jsonml(parsed_outline)
            )
        except json.JSONDecodeError:
            pass

    return {
        "markdown": native_markdown,
        "markdown_chars": len(native_markdown),
        "markdown_sha256": sha256(native_markdown),
        "block_total": int(blocks_payload.get("totalCount") or len(blocks)),
        "blocks_returned": len(blocks),
        "block_types": dict(sorted(block_types.items())),
        "jsonml_success": bool(jsonml_payload.get("success")),
        "jsonml_error": jsonml_error,
        "jsonml_tags": dict(sorted(jsonml_tags.items())),
        "jsonml_max_depth": jsonml_max_depth,
        "native_outline_count": native_outline_count,
    }


def summarize_tokens(values: list[int]) -> dict:
    if not values:
        return {"min": 0, "mean": 0, "median": 0, "p95": 0, "max": 0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int((len(ordered) - 1) * 0.95 + 0.5))
    return {
        "min": min(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": ordered[p95_index],
        "max": max(values),
    }


def analyze_sample(root: Path, native_dir: Path, sample: dict, tokenizer: Any) -> dict:
    raw_path = root / sample["raw_file"]
    raw = raw_path.read_text(encoding="utf-8")
    native = native_stats(native_dir, sample["slug"])

    cleaned_result = clean_markdown(raw, sample["title"])
    cleaned = cleaned_result.cleaned_md
    outline = _extract_outline_v2(cleaned)
    chunked = chunk_document(
        sample["node_id"], sample["title"], cleaned,
        json.dumps(outline, ensure_ascii=False), "FILE",
    )
    leaves = chunked["leaf"]
    parents = chunked["parent"]
    contents = [str(chunk.get("content") or "") for chunk in leaves]
    joined = "\n\n".join(contents)
    current_tokens = [int(chunk.get("token_count") or count_tokens(content)) for chunk, content in zip(leaves, contents)]
    bge_tokens = [len(tokenizer.encode(content, add_special_tokens=True)) for content in contents]

    table_chunks = [content for content in contents if any(TABLE_RE.match(line) for line in content.splitlines())]
    table_chunks_without_separator = [
        content for content in table_chunks
        if not any(TABLE_SEPARATOR_RE.match(line) for line in content.splitlines())
    ]
    unbalanced_fence_chunks = [
        content for content in contents
        if sum(line.lstrip().startswith("```") for line in content.splitlines()) % 2
    ]
    section_paths = [str(chunk.get("section_path") or "") for chunk in leaves]

    result = {
        "slug": sample["slug"],
        "title": sample["title"],
        "node_id": sample["node_id"],
        "folder_path": sample["folder_path"],
        "reason": sample["reason"],
        "raw": {**structural_stats(raw), "sha256": sha256(raw)},
        "live_markdown": {
            "chars": native["markdown_chars"],
            "sha256": native["markdown_sha256"],
            "exactly_matches_raw": native["markdown"] == raw,
            "lexical_recall_from_raw": round(lexical_recall(raw, native["markdown"]), 6),
        },
        "cleaner": {
            **cleaned_result.stats,
            "sha256": sha256(cleaned),
            "lexical_recall_from_raw": round(lexical_recall(raw, cleaned), 6),
            "warnings": cleaned_result.warnings,
        },
        "outline": {
            "count": len(outline),
            "sources": dict(sorted(Counter(entry.get("source", "") for entry in outline).items())),
            "max_level": max((int(entry.get("level") or 0) for entry in outline), default=0),
            "first_paths": [entry.get("path", "") for entry in outline[:8]],
        },
        "classification": classify_document(sample["title"], "FILE", cleaned),
        "current_chunks": {
            "leaf_count": len(leaves),
            "parent_count": len(parents),
            "cl100k_tokens": summarize_tokens(current_tokens),
            "bge_tokens": summarize_tokens(bge_tokens),
            "bge_over_512": sum(value > 512 for value in bge_tokens),
            "bge_over_1200": sum(value > 1200 for value in bge_tokens),
            "lexical_recall_from_cleaned": round(lexical_recall(cleaned, joined), 6),
            "section_path_count": len(set(filter(None, section_paths))),
            "empty_section_path": sum(not path for path in section_paths),
            "section_path_present_in_content": sum(
                bool(path and path in content) for path, content in zip(section_paths, contents)
            ),
            "folder_path_present_in_content": sum(sample["folder_path"] in content for content in contents),
            "table_chunk_count": len(table_chunks),
            "table_chunks_without_separator": len(table_chunks_without_separator),
            "unbalanced_fence_chunks": len(unbalanced_fence_chunks),
        },
        "native": {key: value for key, value in native.items() if key != "markdown"},
    }
    return result


def render_markdown(rows: list[dict]) -> str:
    lines = [
        "# Current v2 pipeline sample audit",
        "",
        "| Sample | Raw chars | Cleaner recall | Outline | Class | Leaves | BGE max | >512 | Table chunks missing separator | Native blocks | Native outline |",
        "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        chunks = row["current_chunks"]
        native = row["native"]
        lines.append(
            f"| {row['slug']} | {row['raw']['chars']} | "
            f"{row['cleaner']['lexical_recall_from_raw']:.4f} | {row['outline']['count']} | "
            f"{row['classification']} | {chunks['leaf_count']} | {chunks['bge_tokens']['max']} | "
            f"{chunks['bge_over_512']} | {chunks['table_chunks_without_separator']} | "
            f"{native['block_total']} | {native['native_outline_count']} |"
        )
    lines.extend(["", "Generated by `analyze_current_pipeline.py`.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / "results" / "current_pipeline_audit.json").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((root / "sample_manifest.json").read_text(encoding="utf-8"))
    native_dir = root / "samples" / "native-download"
    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-small-zh-v1.5", local_files_only=True)
    rows = [analyze_sample(root, native_dir, sample, tokenizer) for sample in manifest]
    payload = {"sample_count": len(rows), "samples": rows}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(rows), encoding="utf-8")
    print(render_markdown(rows))


if __name__ == "__main__":
    main()
