#!/usr/bin/env python3
"""Build a DingTalk-inspired, structure-first chunking candidate.

This is an offline research implementation, not a production ingestion path.
It creates:

1. context chunks capped at 1200 BGE tokens, grouped by native document blocks;
2. retrieval projections capped at 480 BGE tokens for the current bge-small model;
3. a repeated header containing both folder hierarchy and in-document heading path.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from transformers import AutoTokenizer


HEADING_TAGS = {f"h{level}": level for level in range(1, 7)}
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？.!?；;])\s*")
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.:/+-]*|[0-9]+(?:\.[0-9]+)*|[\u4e00-\u9fff]")


def token_count(tokenizer: Any, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=True))


def child_nodes(node: list) -> list:
    attrs_present = len(node) > 1 and isinstance(node[1], dict)
    return node[2 if attrs_present else 1:]


def attrs_of(node: list) -> dict:
    return node[1] if len(node) > 1 and isinstance(node[1], dict) else {}


def leaf_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, list) or not node:
        return ""
    tag = node[0] if isinstance(node[0], str) else ""
    attrs = attrs_of(node)
    if tag == "code" and isinstance(attrs.get("code"), str):
        return attrs["code"]
    if tag in {"img", "image"}:
        alt = str(attrs.get("alt") or attrs.get("title") or "").strip()
        return f"[图片: {alt}]" if alt else "[图片]"
    return "".join(leaf_text(child) for child in child_nodes(node))


def table_rows_from_jsonml(node: list) -> list[list[str]]:
    rows: list[list[str]] = []
    for child in child_nodes(node):
        if not isinstance(child, list) or not child or child[0] != "tr":
            continue
        row = []
        for cell in child_nodes(child):
            if isinstance(cell, list) and cell and cell[0] in {"tc", "th"}:
                row.append(re.sub(r"\s*\n\s*", "<br>", leaf_text(cell)).strip())
        if row:
            rows.append(row)
    return rows


def markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |" for row in padded]
    separator = "| " + " | ".join("---" for _ in range(width)) + " |"
    return "\n".join([lines[0], separator, *lines[1:]])


def jsonml_block(node: list) -> dict | None:
    tag = node[0] if node and isinstance(node[0], str) else "unknown"
    attrs = attrs_of(node)
    if tag in HEADING_TAGS:
        return {
            "kind": "heading",
            "level": HEADING_TAGS[tag],
            "text": leaf_text(node).strip(),
            "block_id": str(attrs.get("uuid") or ""),
        }
    if tag == "table":
        text = markdown_table(table_rows_from_jsonml(node))
        kind = "table"
    elif tag == "code":
        language = str(attrs.get("syntax") or "").strip()
        code = str(attrs.get("code") or leaf_text(node)).rstrip()
        text = f"```{language}\n{code}\n```"
        kind = "code"
    else:
        text = leaf_text(node).strip()
        kind = "paragraph" if tag == "p" else tag
    if not text:
        return None
    return {
        "kind": kind,
        "level": 0,
        "text": text,
        "block_id": str(attrs.get("uuid") or ""),
    }


def blocks_from_jsonml(payload: dict) -> list[dict]:
    if not payload.get("success") or not isinstance(payload.get("jsonml"), str):
        return []
    root = json.loads(payload["jsonml"])
    if not isinstance(root, list) or not root or root[0] not in {"root", "fragment"}:
        return []
    blocks = []
    for node in child_nodes(root):
        if isinstance(node, list):
            block = jsonml_block(node)
            if block:
                blocks.append(block)
    return blocks


def blocks_from_element(payload: dict) -> list[dict]:
    blocks = []
    for row in payload.get("blocks") or []:
        element = row.get("element") or {}
        kind = str(element.get("blockType") or row.get("blockType") or "unknown")
        block_id = str(element.get("id") or "")
        if kind == "heading":
            heading = element.get("heading") or {}
            text = str(heading.get("text") or "").strip()
            if text:
                blocks.append({
                    "kind": "heading",
                    "level": int(heading.get("level") or 1),
                    "text": text,
                    "block_id": block_id,
                })
            continue
        if kind == "table":
            rows = (element.get("table") or {}).get("cells") or []
            text = markdown_table([[str(cell) for cell in cells] for cells in rows])
        else:
            value = element.get(kind) or {}
            text = str(value.get("text") or "").strip() if isinstance(value, dict) else ""
        if text:
            blocks.append({"kind": kind, "level": 0, "text": text, "block_id": block_id})
    return blocks


def apply_heading_paths(blocks: list[dict], title: str) -> list[dict]:
    stack: list[tuple[int, str]] = []
    output = []
    for block in blocks:
        if block["kind"] == "heading":
            level = int(block.get("level") or 1)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, block["text"]))
            continue
        output.append({
            **block,
            "section_path": " > ".join(text for _level, text in stack) or title,
        })
    return output


def split_plain(tokenizer: Any, text: str, limit: int) -> list[str]:
    text = text.strip()
    if not text or token_count(tokenizer, text) <= limit:
        return [text] if text else []
    for separator in ("\n\n", "\n"):
        parts = [part.strip() for part in text.split(separator) if part.strip()]
        if len(parts) > 1:
            return pack_parts(tokenizer, parts, limit, separator)
    sentences = [part.strip() for part in SENTENCE_BOUNDARY_RE.split(text) if part.strip()]
    if len(sentences) > 1:
        return pack_parts(tokenizer, sentences, limit, "")

    pieces = []
    remaining = text
    while remaining:
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if token_count(tokenizer, remaining[:middle]) <= limit:
                low = middle
            else:
                high = middle - 1
        cut = max(1, low)
        pieces.append(remaining[:cut])
        remaining = remaining[cut:]
    return pieces


def pack_parts(tokenizer: Any, parts: list[str], limit: int, joiner: str) -> list[str]:
    output: list[str] = []
    buffer: list[str] = []
    for part in parts:
        candidate = joiner.join([*buffer, part])
        if buffer and token_count(tokenizer, candidate) > limit:
            output.append(joiner.join(buffer))
            buffer = []
        if token_count(tokenizer, part) > limit:
            output.extend(split_plain(tokenizer, part, limit))
        else:
            buffer.append(part)
    if buffer:
        output.append(joiner.join(buffer))
    return output


def split_table(tokenizer: Any, text: str, limit: int) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if token_count(tokenizer, text) <= limit:
        return [text]
    if len(lines) <= 2:
        label = "表格内容：\n"
        piece_limit = max(16, limit - token_count(tokenizer, label) - 4)
        return [label + piece for piece in split_plain(tokenizer, lines[0], piece_limit)]
    header = lines[:2]
    header_text = "\n".join(header)
    groups = []
    buffer = header[:]
    for row in lines[2:]:
        row_with_header = header_text + "\n" + row
        if token_count(tokenizer, row_with_header) > limit:
            if len(buffer) > 2:
                groups.append("\n".join(buffer))
                buffer = header[:]
            row_limit = max(16, limit - token_count(tokenizer, header_text) - 4)
            for piece in split_plain(tokenizer, row, row_limit):
                combined = header_text + "\n" + piece
                if token_count(tokenizer, combined) <= limit:
                    groups.append(combined)
                else:
                    # Extremely dense rows can have tokenizer overhead that is
                    # not additive. Tighten once more against the full header.
                    tighter = max(8, row_limit - (token_count(tokenizer, combined) - limit) - 4)
                    groups.extend(
                        header_text + "\n" + subpiece
                        for subpiece in split_plain(tokenizer, piece, tighter)
                    )
            continue
        candidate = "\n".join([*buffer, row])
        if len(buffer) > 2 and token_count(tokenizer, candidate) > limit:
            groups.append("\n".join(buffer))
            buffer = [*header, row]
        else:
            buffer.append(row)
    if len(buffer) > 2:
        groups.append("\n".join(buffer))
    return groups or split_plain(tokenizer, text, limit)


def split_code(tokenizer: Any, text: str, limit: int) -> list[str]:
    lines = text.splitlines()
    if len(lines) <= 2 or token_count(tokenizer, text) <= limit:
        return [text]
    opener, closer = lines[0], lines[-1] if lines[-1].startswith("```") else "```"
    body = lines[1:-1] if lines[-1].startswith("```") else lines[1:]
    groups = []
    buffer = []
    for line in body:
        candidate = "\n".join([opener, *buffer, line, closer])
        if buffer and token_count(tokenizer, candidate) > limit:
            groups.append("\n".join([opener, *buffer, closer]))
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        groups.append("\n".join([opener, *buffer, closer]))
    return groups or split_plain(tokenizer, text, limit)


def split_block(tokenizer: Any, block: dict, limit: int) -> list[dict]:
    if block["kind"] == "table":
        texts = split_table(tokenizer, block["text"], limit)
    elif block["kind"] == "code":
        texts = split_code(tokenizer, block["text"], limit)
    else:
        texts = split_plain(tokenizer, block["text"], limit)
    return [{**block, "text": text} for text in texts if text.strip()]


def header(folder_path: str, title: str, section_path: str) -> str:
    return (
        f"知识库路径：{folder_path}\n"
        f"文档：{title}\n"
        f"本文目录：{section_path or title}"
    )


def build_context_chunks(
    tokenizer: Any,
    blocks: list[dict],
    folder_path: str,
    title: str,
    target_tokens: int,
    hard_tokens: int,
) -> list[dict]:
    expanded: list[dict] = []
    for block in blocks:
        prefix = header(folder_path, title, block["section_path"])
        body_limit = max(64, hard_tokens - token_count(tokenizer, prefix + "\n\n"))
        expanded.extend(split_block(tokenizer, block, body_limit))

    chunks = []
    buffer: list[dict] = []
    current_path = ""

    def flush() -> None:
        nonlocal buffer, current_path
        if not buffer:
            return
        prefix = header(folder_path, title, current_path)
        body = "\n\n".join(block["text"] for block in buffer)
        context = prefix + "\n\n" + body
        chunks.append({
            "chunk_index": len(chunks),
            "section_path": current_path,
            "header": prefix,
            "body": body,
            "context": context,
            "context_tokens": token_count(tokenizer, context),
            "block_ids": [block.get("block_id", "") for block in buffer if block.get("block_id")],
            "block_types": [block["kind"] for block in buffer],
        })
        buffer = []
        current_path = ""

    for block in expanded:
        path = block["section_path"]
        if buffer and path != current_path:
            flush()
        if not buffer:
            current_path = path
        prefix = header(folder_path, title, current_path)
        candidate_body = "\n\n".join([*(item["text"] for item in buffer), block["text"]])
        candidate_tokens = token_count(tokenizer, prefix + "\n\n" + candidate_body)
        if buffer and candidate_tokens > target_tokens:
            flush()
            current_path = path
        buffer.append(block)
        prefix = header(folder_path, title, current_path)
        actual_body = "\n\n".join(item["text"] for item in buffer)
        if token_count(tokenizer, prefix + "\n\n" + actual_body) > hard_tokens:
            last = buffer.pop()
            flush()
            current_path = path
            buffer = [last]
    flush()
    return chunks


def add_retrieval_projections(
    tokenizer: Any, chunks: list[dict], projection_tokens: int,
) -> None:
    for chunk in chunks:
        prefix = chunk["header"]
        body_limit = max(48, projection_tokens - token_count(tokenizer, prefix + "\n\n"))
        bodies = split_plain(tokenizer, chunk["body"], body_limit)
        chunk["retrieval_projections"] = [
            {
                "projection_index": index,
                "content": prefix + "\n\n" + body,
                "tokens": token_count(tokenizer, prefix + "\n\n" + body),
            }
            for index, body in enumerate(bodies)
        ]


def visible_lexical_recall(source: str, candidate: str) -> float:
    source_counter = Counter(TOKEN_RE.findall(source))
    candidate_counter = Counter(TOKEN_RE.findall(candidate))
    total = sum(source_counter.values())
    if not total:
        return 1.0
    return sum(min(count, candidate_counter[token]) for token, count in source_counter.items()) / total


def summary(values: list[int]) -> dict:
    if not values:
        return {"min": 0, "mean": 0, "median": 0, "max": 0}
    return {
        "min": min(values),
        "mean": round(statistics.fmean(values), 2),
        "median": round(statistics.median(values), 2),
        "max": max(values),
    }


def build_sample(root: Path, tokenizer: Any, sample: dict, args: argparse.Namespace) -> dict:
    native = root / "samples" / "native-download"
    jsonml_payload = json.loads((native / f"{sample['slug']}.jsonml.json").read_text(encoding="utf-8"))
    element_payload = json.loads((native / f"{sample['slug']}.blocks.json").read_text(encoding="utf-8"))
    markdown_payload = json.loads((native / f"{sample['slug']}.markdown.json").read_text(encoding="utf-8"))
    source_markdown = str(markdown_payload.get("markdown") or "")

    blocks = blocks_from_jsonml(jsonml_payload)
    source_mode = "jsonml"
    if not blocks:
        blocks = blocks_from_element(element_payload)
        source_mode = "element_blocks_fallback"
    blocks = apply_heading_paths(blocks, sample["title"])
    chunks = build_context_chunks(
        tokenizer, blocks, sample["folder_path"], sample["title"],
        args.target_tokens, args.hard_tokens,
    )
    add_retrieval_projections(tokenizer, chunks, args.projection_tokens)

    body = "\n\n".join(chunk["body"] for chunk in chunks)
    context_tokens = [chunk["context_tokens"] for chunk in chunks]
    projection_values = [
        projection["tokens"]
        for chunk in chunks for projection in chunk["retrieval_projections"]
    ]
    return {
        "slug": sample["slug"],
        "title": sample["title"],
        "source_mode": source_mode,
        "source_block_count": len(blocks),
        "section_count": len({block["section_path"] for block in blocks}),
        "context_chunk_count": len(chunks),
        "context_tokens": summary(context_tokens),
        "context_over_hard_limit": sum(value > args.hard_tokens for value in context_tokens),
        "retrieval_projection_count": len(projection_values),
        "projection_tokens": summary(projection_values),
        "projection_over_limit": sum(value > args.projection_tokens for value in projection_values),
        "folder_header_coverage": sum(sample["folder_path"] in chunk["context"] for chunk in chunks),
        "section_header_coverage": sum(chunk["section_path"] in chunk["context"] for chunk in chunks),
        "visible_lexical_recall_from_markdown": round(visible_lexical_recall(source_markdown, body), 6),
        "chunks": chunks,
    }


def render_markdown(rows: list[dict]) -> str:
    lines = [
        "# DingTalk-style candidate audit",
        "",
        "| Sample | Native source | Blocks | Sections | Context chunks | Context token max | Retrieval projections | Projection max | Folder headers | Section headers |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['slug']} | {row['source_mode']} | {row['source_block_count']} | "
            f"{row['section_count']} | {row['context_chunk_count']} | {row['context_tokens']['max']} | "
            f"{row['retrieval_projection_count']} | {row['projection_tokens']['max']} | "
            f"{row['folder_header_coverage']}/{row['context_chunk_count']} | "
            f"{row['section_header_coverage']}/{row['context_chunk_count']} |"
        )
    lines.extend(["", "Generated by `dingtalk_style_candidate.py`.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--target-tokens", type=int, default=900)
    parser.add_argument("--hard-tokens", type=int, default=1200)
    parser.add_argument("--projection-tokens", type=int, default=480)
    args = parser.parse_args()
    root = args.root.resolve()
    output_dir = root / "results" / "candidate_chunks"
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-small-zh-v1.5", local_files_only=True)
    tokenizer.model_max_length = 1_000_000
    manifest = json.loads((root / "sample_manifest.json").read_text(encoding="utf-8"))
    rows = []
    for sample in manifest:
        row = build_sample(root, tokenizer, sample, args)
        rows.append(row)
        (output_dir / f"{sample['slug']}.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    compact = [{key: value for key, value in row.items() if key != "chunks"} for row in rows]
    payload = {
        "config": {
            "target_tokens": args.target_tokens,
            "hard_tokens": args.hard_tokens,
            "projection_tokens": args.projection_tokens,
        },
        "samples": compact,
    }
    (root / "results" / "dingtalk_style_candidate.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = render_markdown(compact)
    (root / "results" / "dingtalk_style_candidate.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
