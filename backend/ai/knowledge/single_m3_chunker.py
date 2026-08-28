"""Single-level, BGE-M3-sized document chunking.

This module deliberately returns the existing ``persist_chunk_result`` contract
(``{"leaf": [...], "parent": []}``) so the first rollout does not require a
database schema migration.  In this strategy ``depth=1`` means searchable
chunk; no parent chunks are created.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Iterable, List, Optional


TARGET_TOKENS = 800
MAX_TOKENS = 1200
MIN_TOKENS = 120
MAX_HEADER_CHARS = 900

_tokenizer: Any = None
_tokenizer_error: Exception | None = None


def _get_tokenizer() -> Any:
    global _tokenizer, _tokenizer_error
    if _tokenizer is not None:
        return _tokenizer
    if _tokenizer_error is not None:
        raise RuntimeError("BGE-M3 tokenizer is unavailable") from _tokenizer_error

    model_name = os.getenv("BGE_M3_MODEL_NAME", "BAAI/bge-m3")
    try:
        from transformers import AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            local_files_only=os.getenv("HF_HUB_OFFLINE", "1") != "0",
        )
        # We use the tokenizer to measure complete source text before
        # splitting; the actual model only receives the resulting <=1200-token
        # chunks.
        _tokenizer.model_max_length = 1_000_000
        return _tokenizer
    except Exception as exc:  # pragma: no cover - depends on deployment assets
        _tokenizer_error = exc
        raise RuntimeError(
            f"Unable to load BGE-M3 tokenizer from {model_name!r}; "
            "install the model before using KB_CHUNK_STRATEGY=single_m3"
        ) from exc


def count_m3_tokens(text: str, tokenizer: Any = None) -> int:
    encoder = tokenizer or _get_tokenizer()
    return len(encoder.encode(text, add_special_tokens=True))


def _outline_entries(outline_json: str) -> list[dict]:
    if not outline_json:
        return []
    try:
        value = json.loads(outline_json)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _sections(content: str, outline: list[dict]) -> list[tuple[str, str]]:
    lines = content.splitlines()
    if not outline:
        return [("", content.strip())]

    # The legacy Markdown outline may mistake a line inside fenced code for a
    # heading.  Such a boundary would split the fence before the atomic block
    # splitter sees it, so discard outline entries that fall inside code.
    inside_fence: list[bool] = []
    in_fence = False
    for line in lines:
        inside_fence.append(in_fence)
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
    valid_outline = []
    for entry in outline:
        line_index = max(0, int(entry.get("line") or 1) - 1)
        if line_index < len(inside_fence) and not inside_fence[line_index]:
            valid_outline.append(entry)
    outline = valid_outline
    if not outline:
        return [("", content.strip())]

    result: list[tuple[str, str]] = []
    first = max(0, min(len(lines), int(outline[0].get("line") or 1) - 1))
    if first:
        result.append(("", "\n".join(lines[:first]).strip()))
    for index, entry in enumerate(outline):
        start = max(0, min(len(lines), int(entry.get("line") or 1) - 1))
        end = len(lines)
        if index + 1 < len(outline):
            end = max(start, min(len(lines), int(outline[index + 1].get("line") or 1) - 1))
        body = "\n".join(lines[start:end]).strip()
        if body:
            result.append((str(entry.get("path") or entry.get("title") or ""), body))
    return result or [("", content.strip())]


def _compact_path(path: str, max_parts: int = 4) -> str:
    parts = [part.strip() for part in re.split(r"\s*/\s*", path or "") if part.strip()]
    if len(parts) > max_parts:
        parts = [parts[0], "...", *parts[-(max_parts - 2):]]
    return " / ".join(parts)


def _header(folder_path: str, title: str, section_path: str) -> str:
    folder = _compact_path(folder_path) or "未归档"
    section = section_path.strip() or title
    text = (
        f"知识库路径：{folder}\n"
        f"文档：{title}\n"
        f"本文目录：{section}"
    )
    return text[:MAX_HEADER_CHARS]


def _atomic_spans(lines: list[str]) -> Iterable[str]:
    """Yield paragraphs, fenced code blocks and contiguous table blocks."""
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        line = lines[index]
        if line.lstrip().startswith("```"):
            end = index + 1
            while end < len(lines):
                if lines[end].lstrip().startswith("```"):
                    end += 1
                    break
                end += 1
            yield "\n".join(lines[index:end]).strip()
            index = end
            continue
        if line.lstrip().startswith("|"):
            end = index + 1
            while end < len(lines) and lines[end].lstrip().startswith("|"):
                end += 1
            yield "\n".join(lines[index:end]).strip()
            index = end
            continue
        end = index + 1
        while end < len(lines) and lines[end].strip():
            if lines[end].lstrip().startswith(("```", "|")):
                break
            end += 1
        yield "\n".join(lines[index:end]).strip()
        index = end


def _split_plain(text: str, tokenizer: Any, limit: int) -> list[str]:
    if count_m3_tokens(text, tokenizer) <= limit:
        return [text]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) > 1:
        return _pack(paragraphs, tokenizer, limit, "\n\n")
    sentences = [part.strip() for part in re.split(r"(?<=[。！？.!?；;])\s*", text) if part.strip()]
    if len(sentences) > 1:
        return _pack(sentences, tokenizer, limit, "")

    pieces: list[str] = []
    remaining = text
    while remaining:
        low, high = 1, len(remaining)
        while low < high:
            middle = (low + high + 1) // 2
            if count_m3_tokens(remaining[:middle], tokenizer) <= limit:
                low = middle
            else:
                high = middle - 1
        cut = max(1, low)
        pieces.append(remaining[:cut])
        remaining = remaining[cut:]
    return pieces


def _pack(parts: list[str], tokenizer: Any, limit: int, joiner: str) -> list[str]:
    result: list[str] = []
    buffer: list[str] = []
    for part in parts:
        candidate = joiner.join([*buffer, part])
        if buffer and count_m3_tokens(candidate, tokenizer) > limit:
            result.append(joiner.join(buffer))
            buffer = []
        if count_m3_tokens(part, tokenizer) > limit:
            result.extend(_split_plain(part, tokenizer, limit))
        else:
            buffer.append(part)
    if buffer:
        result.append(joiner.join(buffer))
    return result


def _split_table(text: str, tokenizer: Any, limit: int) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    if count_m3_tokens(text, tokenizer) <= limit:
        return [text]
    if len(lines) < 2:
        return _split_plain(text, tokenizer, limit)
    header = lines[:2]
    groups: list[str] = []
    buffer = header[:]
    for row in lines[2:]:
        candidate = "\n".join([*buffer, row])
        if len(buffer) > 2 and count_m3_tokens(candidate, tokenizer) > limit:
            groups.append("\n".join(buffer))
            buffer = header[:]
        if count_m3_tokens("\n".join([*buffer, row]), tokenizer) > limit:
            row_limit = max(16, limit - count_m3_tokens("\n".join(header), tokenizer))
            groups.extend(
                "\n".join([*header, piece])
                for piece in _split_plain(row, tokenizer, row_limit)
            )
        else:
            buffer.append(row)
    if len(buffer) > 2:
        groups.append("\n".join(buffer))
    return groups or _split_plain(text, tokenizer, limit)


def _split_code(text: str, tokenizer: Any, limit: int) -> list[str]:
    lines = text.splitlines()
    if len(lines) <= 2 or count_m3_tokens(text, tokenizer) <= limit:
        return [text]
    opener = lines[0]
    closer = lines[-1] if lines[-1].lstrip().startswith("```") else "```"
    body = lines[1:-1] if lines[-1].lstrip().startswith("```") else lines[1:]
    result: list[str] = []
    buffer: list[str] = []
    for line in body:
        candidate = "\n".join([opener, *buffer, line, closer])
        if buffer and count_m3_tokens(candidate, tokenizer) > limit:
            result.append("\n".join([opener, *buffer, closer]))
            buffer = []
        buffer.append(line)
    if buffer:
        result.append("\n".join([opener, *buffer, closer]))
    return result or _split_plain(text, tokenizer, limit)


def _split_block(text: str, tokenizer: Any, limit: int) -> list[str]:
    stripped = text.lstrip()
    if stripped.startswith("```"):
        return _split_code(text, tokenizer, limit)
    if stripped.startswith("|"):
        return _split_table(text, tokenizer, limit)
    return _split_plain(text, tokenizer, limit)


def chunk_document_single_m3(
    doc_id: str,
    title: str,
    content: str,
    outline_json: str = "",
    node_type: str = "FILE",
    folder_path: str = "",
    *,
    tokenizer: Any = None,
    target_tokens: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> dict:
    del node_type  # reserved for future type-specific strategies
    if not content or not content.strip():
        return {"leaf": [], "parent": []}
    encoder = tokenizer or _get_tokenizer()
    leaves: list[dict] = []

    for section_path, section_text in _sections(content, _outline_entries(outline_json)):
        prefix = _header(folder_path, title, section_path or title)
        prefix_tokens = count_m3_tokens(prefix, encoder)
        body_limit = max(32, max_tokens - prefix_tokens - 2)
        target_body = max(32, target_tokens - prefix_tokens - 2)
        blocks: list[str] = []
        for block in _atomic_spans(section_text.splitlines()):
            blocks.extend(_split_block(block, encoder, body_limit))

        buffer: list[str] = []
        for block in blocks:
            candidate_body = "\n\n".join([*buffer, block])
            if buffer and count_m3_tokens(candidate_body, encoder) > target_body:
                leaves.append(_make_leaf(doc_id, prefix, section_path or title, buffer, encoder))
                buffer = []
            buffer.append(block)
        if buffer:
            leaves.append(_make_leaf(doc_id, prefix, section_path or title, buffer, encoder))

    for index, leaf in enumerate(leaves):
        leaf["chunk_index"] = index
    return {"leaf": leaves, "parent": []}


def _make_leaf(
    doc_id: str,
    prefix: str,
    section_path: str,
    blocks: list[str],
    tokenizer: Any,
) -> dict:
    body = "\n\n".join(blocks).strip()
    content = f"{prefix}\n\n{body}".strip()
    return {
        "doc_id": doc_id,
        "chunk_index": 0,
        "content": content,
        "token_count": count_m3_tokens(content, tokenizer),
        "heading": section_path,
        "section_path": section_path,
        "depth": 1,
        "chunk_type": "single",
    }
