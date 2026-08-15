"""RAG v3 chunker — outline-driven parent-child chunking.

Strategy:
  - Leaf chunks:  220-420 tokens (hard cap 512), for embedding
  - Parent chunks: 600-1200 tokens (same-section leaf aggregation), for LLM context
  - Outline-driven: uses pre-computed outline JSON (from kb_documents.outline)
  - Short docs (<500 chars) → single leaf, no parent
  - Long docs (>3K chars) → leaf + parent hierarchy
  - Atomic protection: code blocks, table rows, list items never split mid-block
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

# ── token counting ──────────────────────────────────────────────────

try:
    import tiktoken
    _encoder = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_encoder.encode(text))
except Exception:
    def count_tokens(text: str) -> int:
        chinese = len(re.findall(r'[一-鿿]', text))
        other = len(text) - chinese
        return int(chinese * 1.8 + other * 0.3)


# ── v3 sizing constants ─────────────────────────────────────────────

LEAF_TARGET = 320
LEAF_MIN    = 150
LEAF_MAX    = 512
PARENT_TARGET = 800
PARENT_MAX    = 1200
PARENT_MIN_SECTION_TOKENS = 300

SHORT_DOC_CHARS = 500
LONG_DOC_CHARS  = 3000

# DB column limit for section_path
SECTION_PATH_MAX_LEN = 1020


def _safe_path(path: str) -> str:
    """Truncate section_path to fit DB column."""
    if len(path) <= SECTION_PATH_MAX_LEN:
        return path
    return path[:SECTION_PATH_MAX_LEN - 3] + "..."


# ── document classification (kept from v2) ──────────────────────────

MEETING_KEYWORDS = [
    "会议纪要", "周报", "日报", "月报", "总结", "晨会", "例会",
    "周会", "月度会议", "周例会", "复盘",
]


def classify_document(title: str, node_type: str, content: str) -> str:
    """Return: 'structured' | 'meeting' | 'table' | 'text'."""
    if node_type.upper() in ("WORKBOOK", "TABLE"):
        return "table"
    pipe_lines = len([l for l in content.split("\n") if l.strip().startswith("|")])
    total_lines = max(content.count("\n"), 1)
    if pipe_lines > 10 and pipe_lines / total_lines > 0.3:
        return "table"
    title_lower = title.lower()
    for kw in MEETING_KEYWORDS:
        if kw in title_lower:
            return "meeting"
    h2_count = len(re.findall(r'^##\s', content, re.MULTILINE))
    if h2_count >= 2:
        return "structured"
    return "text"


# ── helpers ─────────────────────────────────────────────────────────

def _fixed_window(
    text: str,
    target: int = LEAF_TARGET,
    min_tokens: int = LEAF_MIN,
    max_tokens: int = LEAF_MAX,
) -> List[str]:
    """Split text into fixed-token windows at paragraph boundaries."""
    paragraphs = text.split("\n\n")
    windows: List[str] = []
    buf: List[str] = []
    buf_tokens: int = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        para_tokens = count_tokens(para)
        if para_tokens > max_tokens:
            if buf:
                windows.append("\n\n".join(buf))
                buf, buf_tokens = [], 0
            sentences = re.split(r'(?<=[。！？.!?])\s*', para)
            if len(sentences) <= 1:
                lines = para.split("\n")
                sub_buf, sub_tokens = [], 0
                for line in lines:
                    lt = count_tokens(line)
                    # Oversize single line: force-split by character count
                    if lt > max_tokens:
                        if sub_buf and sub_tokens >= min_tokens:
                            windows.append("\n".join(sub_buf))
                            sub_buf, sub_tokens = [], 0
                        elif sub_buf:
                            # merge small buffer into this split
                            line = "\n".join(sub_buf) + "\n" + line
                            sub_buf, sub_tokens = [], 0
                        for chunk in _force_split_long(line, max_tokens):
                            windows.append(chunk)
                        continue
                    if sub_tokens + lt > target and sub_tokens >= min_tokens:
                        windows.append("\n".join(sub_buf))
                        sub_buf, sub_tokens = [], 0
                    sub_buf.append(line)
                    sub_tokens += lt
                if sub_buf:
                    windows.append("\n".join(sub_buf))
            else:
                sub_buf, sub_tokens = [], 0
                for sent in sentences:
                    st = count_tokens(sent)
                    if sub_tokens + st > target and sub_tokens >= min_tokens:
                        windows.append(" ".join(sub_buf))
                        sub_buf, sub_tokens = [], 0
                    sub_buf.append(sent)
                    sub_tokens += st
                if sub_buf:
                    windows.append(" ".join(sub_buf))
        elif buf_tokens + para_tokens <= target or buf_tokens < min_tokens:
            buf.append(para)
            buf_tokens += para_tokens
        else:
            windows.append("\n\n".join(buf))
            buf, buf_tokens = [para], para_tokens

    if buf:
        windows.append("\n\n".join(buf))
    bounded: List[str] = []
    for window in windows:
        if count_tokens(window) <= max_tokens:
            bounded.append(window)
        else:
            bounded.extend(_force_split_long(window, max_tokens))
    return bounded


def _parse_row(line: str) -> List[str]:
    stripped = line.strip().strip("|")
    return [c.strip() for c in stripped.split("|")]


def _force_split_long(text: str, max_tokens: int) -> List[str]:
    """Force-split a single long string by approximate token boundaries.
    Used as last resort when paragraph/sentence/line splitting all fail.
    """
    chunks: List[str] = []
    start = 0
    while start < len(text):
        remaining = text[start:]
        if count_tokens(remaining) <= max_tokens:
            chunks.append(remaining)
            break
        low, high, best = 1, len(remaining), 1
        while low <= high:
            mid = (low + high) // 2
            if count_tokens(remaining[:mid]) <= max_tokens:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        chunks.append(remaining[:best])
        start += best
    return chunks


# ── atomic block detection ──────────────────────────────────────────

_ATOMIC_PATTERNS = [
    re.compile(r"^```"),
    re.compile(r"^\|"),
    re.compile(r"^\s*[-*+]\s"),
    re.compile(r"^\s*\d+[.)]\s"),
]


def _is_atomic_line(line: str) -> bool:
    stripped = line.rstrip()
    for pat in _ATOMIC_PATTERNS:
        if pat.match(stripped):
            return True
    return False


def _atomic_span_end(lines: List[str], start: int) -> int:
    """Return exclusive end index for atomic block starting at `start`."""
    stripped = lines[start].rstrip()
    if stripped.startswith("```"):
        i = start
        while i < len(lines):
            if lines[i].rstrip().startswith("```") and i > start:
                return i + 1
            i += 1
        return len(lines)
    if stripped.strip().startswith("|"):
        i = start
        while i < len(lines):
            if not lines[i].strip().startswith("|"):
                break
            i += 1
        return i
    # list
    list_pat = re.compile(r"^\s*[-*+]\s|^\s*\d+[.)]\s")
    i = start
    while i < len(lines):
        s = lines[i]
        if not list_pat.match(s) and s.strip():
            break
        if not s.strip():
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and list_pat.match(lines[j]):
                i = j
                continue
            break
        i += 1
    return i


# ── outline parsing ─────────────────────────────────────────────────

def _parse_outline(outline_json: str) -> List[dict]:
    if not outline_json or not outline_json.strip():
        return []
    try:
        data = json.loads(outline_json)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _build_sections(
    lines: List[str], outline: List[dict]
) -> List[Tuple[dict, int, int]]:
    """Return [(entry, start_line_0based, end_line_exclusive), ...]."""
    if not outline:
        return [({"level": 0, "title": "", "line": 1, "path": "", "source": "none"}, 0, len(lines))]
    sections: List[Tuple[dict, int, int]] = []
    first_start = min(max(0, outline[0]["line"] - 1), len(lines))
    if first_start > 0:
        sections.append((
            {"level": 0, "title": "", "line": 1, "path": "",
             "source": "synthetic_preamble"},
            0, first_start,
        ))
    for i, entry in enumerate(outline):
        start = min(max(0, entry["line"] - 1), len(lines))
        end = min(outline[i + 1]["line"] - 1, len(lines)) if i + 1 < len(outline) else len(lines)
        end = max(end, start)
        if start < len(lines):
            sections.append((entry, start, end))
    return sections


# ── leaf chunk builders ─────────────────────────────────────────────

def _make_leaf(lines: List[str], heading: str, section_path: str) -> dict:
    text = "\n".join(lines).strip()
    return {
        "content": text,
        "token_count": count_tokens(text),
        "heading": heading,
        "section_path": _safe_path(section_path),
        "depth": 1,
        "chunk_type": "paragraph",
        "doc_id": "",       # filled later
        "chunk_index": 0,   # filled later
    }


def _chunk_section_leaf(
    section_lines: List[str], heading: str, section_path: str
) -> List[dict]:
    """Split section lines into leaf chunks, respecting atomic blocks."""
    if not section_lines:
        return []
    chunks: List[dict] = []
    buf_lines: List[str] = []
    buf_tokens: int = 0
    i = 0

    while i < len(section_lines):
        line = section_lines[i]

        if _is_atomic_line(line):
            end = _atomic_span_end(section_lines, i)
            block_lines = section_lines[i:end]
            block_text = "\n".join(block_lines)
            block_tokens = count_tokens(block_text)

            if block_tokens > LEAF_MAX:
                if buf_lines:
                    chunks.append(_make_leaf(buf_lines, heading, section_path))
                    buf_lines, buf_tokens = [], 0
                for win in _fixed_window(block_text, LEAF_TARGET, LEAF_MIN, LEAF_MAX):
                    chunks.append(_make_leaf([win], heading, section_path))
                i = end
                continue

            if buf_tokens + block_tokens <= LEAF_TARGET:
                buf_lines.extend(block_lines)
                buf_tokens += block_tokens
            else:
                if buf_lines:
                    chunks.append(_make_leaf(buf_lines, heading, section_path))
                buf_lines, buf_tokens = list(block_lines), block_tokens
            i = end
            continue

        # regular line
        lt = count_tokens(line) if line.strip() else 1

        # Oversize single line → split via fixed window
        if lt > LEAF_MAX:
            if buf_lines:
                chunks.append(_make_leaf(buf_lines, heading, section_path))
                buf_lines, buf_tokens = [], 0
            for win in _fixed_window(line, LEAF_TARGET, LEAF_MIN, LEAF_MAX):
                chunks.append(_make_leaf([win], heading, section_path))
            i += 1
            continue

        if buf_tokens + lt <= LEAF_TARGET or buf_tokens < LEAF_MIN:
            buf_lines.append(line)
            buf_tokens += lt
        else:
            if buf_lines:
                chunks.append(_make_leaf(buf_lines, heading, section_path))
            buf_lines, buf_tokens = [line], lt
        i += 1

    if buf_lines:
        if buf_tokens < LEAF_MIN and chunks:
            prev = chunks[-1]
            merged = prev["content"] + "\n" + "\n".join(buf_lines)
            if count_tokens(merged) <= LEAF_MAX:
                prev["content"] = merged
                prev["token_count"] = count_tokens(merged)
            else:
                chunks.append(_make_leaf(buf_lines, heading, section_path))
        else:
            chunks.append(_make_leaf(buf_lines, heading, section_path))

    return chunks


# ── parent chunk builder ────────────────────────────────────────────

def _make_parent(parts: List[str], tokens: int, section_path: str) -> dict:
    return {
        "content": "\n\n".join(parts).strip(),
        "token_count": tokens,
        "heading": "",
        "section_path": _safe_path(section_path),
        "depth": 0,
        "chunk_type": "parent",
        "doc_id": "",       # filled later
        "chunk_index": 0,   # filled later
    }


def _build_parent_chunks(leaf_chunks: List[dict]) -> List[dict]:
    """Aggregate leaf chunks per section_path into parent chunks."""
    if not leaf_chunks:
        return []
    groups: Dict[str, List[dict]] = {}
    for c in leaf_chunks:
        sp = c.get("section_path", "") or ""
        groups.setdefault(sp, []).append(c)

    parents: List[dict] = []
    for sp, children in groups.items():
        total_tokens = sum(c["token_count"] for c in children)
        if total_tokens < PARENT_MIN_SECTION_TOKENS:
            continue
        buf: List[str] = []
        buf_tokens: int = 0
        for child in children:
            ct = child["token_count"]
            if buf_tokens + ct <= PARENT_TARGET:
                buf.append(child["content"])
                buf_tokens += ct
            else:
                if buf:
                    parents.append(_make_parent(buf, buf_tokens, sp))
                buf = [child["content"]]
                buf_tokens = ct
        if buf:
            parents.append(_make_parent(buf, buf_tokens, sp))
    return parents


# ── strategy implementations ────────────────────────────────────────

def _resolve_path(title: str, outline: Optional[List[dict]]) -> str:
    if outline:
        for e in outline:
            if e.get("path"):
                return e["path"]
    return title


def _plain_leaf(content: str, title: str, outline: Optional[List[dict]]) -> List[dict]:
    return [_make_leaf([content], title, _resolve_path(title, outline))]


def _chunk_structured_v3(content: str, title: str, outline: List[dict]) -> List[dict]:
    lines = content.split("\n")
    sections = _build_sections(lines, outline)
    all_chunks: List[dict] = []
    for entry, start, end in sections:
        heading = entry.get("title", "")
        # Synthetic preamble entries deliberately have an empty path; keep
        # their content associated with the document instead of "".
        sp = entry.get("path") or title
        all_chunks.extend(_chunk_section_leaf(lines[start:end], heading, sp))
    return all_chunks or _chunk_text_v3(content, title, outline)


def _chunk_table_v3(content: str, title: str, outline: Optional[List[dict]]) -> List[dict]:
    # Preserve the original representation: the old key/value conversion
    # dropped surrounding prose, headers, separators, and sometimes rows.
    return _chunk_section_leaf(content.split("\n"), title,
                               _resolve_path(title, outline))


def _chunk_meeting_v3(content: str, title: str, outline: Optional[List[dict]]) -> List[dict]:
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return []
    sp = _resolve_path(title, outline)
    chunks: List[dict] = []
    buf, bt = [], 0
    for para in paragraphs:
        pt = count_tokens(para)
        if bt + pt <= LEAF_TARGET or bt < LEAF_MIN:
            buf.append(para)
            bt += pt
        else:
            chunks.append(_make_leaf(buf, title, sp))
            buf, bt = [para], pt
    if buf:
        chunks.append(_make_leaf(buf, title, sp))
    return chunks


def _chunk_text_v3(content: str, title: str, outline: Optional[List[dict]]) -> List[dict]:
    sp = _resolve_path(title, outline)
    windows = _fixed_window(content, LEAF_TARGET, LEAF_MIN, LEAF_MAX)
    return [_make_leaf([w], title, sp) for w in windows] if windows else []


# ── post-processing: merge tiny adjacent leaves ─────────────────────

def _merge_tiny_leaves(leaf_chunks: List[dict]) -> List[dict]:
    """Merge adjacent leaf chunks that are too small (< LEAF_MIN tokens).

    This handles the case where outline extraction produced very fine-grained
    sections (e.g. table rows treated as headings), resulting in single-line chunks.
    """
    if len(leaf_chunks) <= 1:
        return leaf_chunks

    merged: List[dict] = []
    buf_content: List[str] = []
    buf_tokens: int = 0
    buf_path: str = ""
    buf_heading: str = ""

    def _flush():
        if not buf_content:
            return
        text = "\n".join(buf_content).strip()
        path = buf_path or (leaf_chunks[0].get("section_path", "") if leaf_chunks else "")
        merged.append({
            "content": text,
            "token_count": count_tokens(text),
            "heading": buf_heading,
            "section_path": _safe_path(path),
            "depth": 1,
            "chunk_type": "paragraph",
            "doc_id": "",
            "chunk_index": 0,
        })

    for c in leaf_chunks:
        ct = c["token_count"]
        # If buffer is empty, start new
        if not buf_content:
            buf_content = [c["content"]]
            buf_tokens = ct
            buf_path = c.get("section_path", "")
            buf_heading = c.get("heading", "")
            continue

        # If adding this tiny chunk to buffer stays under LEAF_TARGET, merge it
        if buf_tokens + ct <= LEAF_TARGET:
            buf_content.append(c["content"])
            buf_tokens += ct
            # Use the longer section_path
            if len(c.get("section_path", "")) > len(buf_path):
                buf_path = c["section_path"]
            continue

        # Buffer is full enough — flush and start new
        _flush()
        buf_content = [c["content"]]
        buf_tokens = ct
        buf_path = c.get("section_path", "")
        buf_heading = c.get("heading", "")

    _flush()
    return merged


# ── public API ──────────────────────────────────────────────────────

def chunk_document(
    doc_id: str,
    title: str,
    content: str,
    outline_json: str = "",
    node_type: str = "FILE",
) -> Dict[str, List[dict]]:
    """Chunk a single document with v3 parent-child hierarchy.

    Returns {"leaf": [...], "parent": [...]} where each chunk has:
      content, token_count, heading, section_path, depth (0|1), chunk_type
    """
    if not content or not content.strip():
        return {"leaf": [], "parent": []}

    outline = _parse_outline(outline_json)
    doc_type = classify_document(title, node_type, content)

    # Choose strategy
    if len(content) < SHORT_DOC_CHARS:
        leaf = _plain_leaf(content, title, outline)
    elif doc_type == "structured" and outline:
        leaf = _chunk_structured_v3(content, title, outline)
    elif doc_type == "meeting":
        leaf = _chunk_meeting_v3(content, title, outline)
    elif doc_type == "table":
        leaf = _chunk_table_v3(content, title, outline)
    else:
        leaf = _chunk_text_v3(content, title, outline)

    # Merge adjacent tiny leaves (handles fine-grained outlines like table-rows-as-headings)
    leaf = _merge_tiny_leaves(leaf)

    # Enforce the real hard limit after every strategy and after merging.
    bounded_leaf: List[dict] = []
    for chunk in leaf:
        text = chunk.get("content", "")
        if count_tokens(text) <= LEAF_MAX:
            chunk["token_count"] = count_tokens(text)
            bounded_leaf.append(chunk)
        else:
            for window in _force_split_long(text, LEAF_MAX):
                bounded_leaf.append(_make_leaf(
                    [window], chunk.get("heading", ""),
                    chunk.get("section_path", title),
                ))
    leaf = bounded_leaf or _chunk_text_v3(content, title, outline)

    # Build parent chunks for long docs
    parent: List[dict] = []
    if len(content) >= LONG_DOC_CHARS:
        parent = _build_parent_chunks(leaf)

    # Assign doc_id + index
    for i, c in enumerate(leaf):
        c["doc_id"] = doc_id
        c["chunk_index"] = i
    for i, c in enumerate(parent):
        c["doc_id"] = doc_id
        c["chunk_index"] = i + 100000  # temp offset, fixed after parent_ids assigned

    return {"leaf": leaf, "parent": parent}
