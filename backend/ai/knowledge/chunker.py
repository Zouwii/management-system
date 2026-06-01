"""Document chunker — split Markdown documents into retrievable chunks.

Strategy:
  structured  — heading-based split (## as primary split point)
  meeting     — paragraph aggregation (for meeting notes / weekly reports)
  table       — row grouping with header prefix (workbook / .axls)
  text        — fixed sliding window
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Token counting
try:
    import tiktoken
    _encoder = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_encoder.encode(text))
except Exception:
    def count_tokens(text: str) -> int:
        # Fallback: ~1.8 tokens per Chinese char, ~0.75 per English word
        chinese = len(re.findall(r'[一-鿿]', text))
        other = len(text) - chinese
        return int(chinese * 1.8 + other * 0.3)


# ── document classification ──────────────────────────────────────

MEETING_KEYWORDS = [
    "会议纪要", "周报", "日报", "月报", "总结", "晨会", "例会",
    "周会", "月度会议", "周例会", "复盘",
]


def classify_document(title: str, node_type: str, content: str) -> str:
    """Return: 'structured' | 'meeting' | 'table' | 'text'."""
    if node_type.upper() in ("WORKBOOK", "TABLE"):
        return "table"

    # Detect table-heavy content (markdown tables with many | pipes)
    pipe_lines = len([l for l in content.split("\n") if l.strip().startswith("|")])
    total_lines = max(content.count("\n"), 1)
    if pipe_lines > 10 and pipe_lines / total_lines > 0.3:
        return "table"

    title_lower = title.lower()
    for kw in MEETING_KEYWORDS:
        if kw in title_lower:
            return "meeting"

    # Check for structured heading hierarchy
    h2_count = len(re.findall(r'^##\s', content, re.MULTILINE))
    if h2_count >= 2:
        return "structured"

    return "text"


# ── structured: heading-based split ──────────────────────────────

def chunk_structured(
    content: str,
    title: str,
    *,
    target_tokens: int = 800,
    min_tokens: int = 100,
    max_tokens: int = 1200,
    overlap_tokens: int = 150,
) -> List[Dict[str, Any]]:
    """Split on ## headings. If a section exceeds max_tokens, drill down to ###."""
    sections = _split_by_headings(content)
    if not sections:
        return []

    chunks: List[Dict[str, Any]] = []
    buf_lines: List[str] = []
    buf_heading: str = ""
    buf_tokens: int = 0

    def _emit(lines: List[str], heading: str) -> dict:
        text = "\n".join(lines).strip()
        # Overlap: keep tail of previous chunk as prefix
        if chunks and overlap_tokens > 0:
            prev_text = chunks[-1]["content"]
            prev_tokens = count_tokens(prev_text)
            if prev_tokens > overlap_tokens:
                overlap = _tail_tokens(prev_text, overlap_tokens)
                text = overlap + "\n" + text
        meta = f"[来源: {title}]"
        if heading:
            meta += f"\n[章节: {heading}]"
        return {
            "content": f"{meta}\n\n{text}",
            "token_count": count_tokens(text),
            "heading": heading,
        }

    for sec_heading, sec_body in sections:
        sec_tokens = count_tokens(sec_body)

        # Section too large → drill down to ###
        if sec_tokens > max_tokens:
            sub_sections = _split_by_sub_headings(sec_body)
            if sub_sections:
                for sub_h, sub_body in sub_sections:
                    sub_tokens = count_tokens(sub_body)
                    if sub_tokens > max_tokens:
                        # Still too large → fixed window within this sub-section
                        sub_hdr = f"{sec_heading} > {sub_h}" if sec_heading else sub_h
                        for win in _fixed_window(sub_body, target_tokens, min_tokens, max_tokens):
                            chunks.append(_emit([win], sub_hdr))
                    else:
                        hdr = f"{sec_heading} > {sub_h}" if sec_heading else sub_h
                        chunks.append(_emit([sub_body], hdr))
                continue
            # No sub-headings found, fall through to fixed window
            for win in _fixed_window(sec_body, target_tokens, min_tokens, max_tokens):
                chunks.append(_emit([win], sec_heading))
            continue

        # Try to add to current buffer
        if buf_tokens + sec_tokens <= target_tokens:
            buf_lines.append(sec_body)
            buf_tokens += sec_tokens
            if not buf_heading and sec_heading:
                buf_heading = sec_heading
            elif buf_heading and sec_heading:
                buf_heading = buf_heading.split(" > ")[0]
        else:
            # Flush buffer
            if buf_lines and buf_tokens >= min_tokens:
                chunks.append(_emit(buf_lines, buf_heading))
            elif buf_lines:
                # Too small, merge with current section if possible
                sec_body = "\n".join(buf_lines) + "\n" + sec_body
                sec_tokens = count_tokens(sec_body)
                if sec_tokens > max_tokens:
                    for win in _fixed_window(sec_body, target_tokens, min_tokens, max_tokens):
                        chunks.append(_emit([win], sec_heading))
                else:
                    chunks.append(_emit([sec_body], sec_heading))
                buf_lines, buf_heading, buf_tokens = [], "", 0
                continue
            else:
                chunks.append(_emit([sec_body], sec_heading))
            buf_lines, buf_heading, buf_tokens = [], sec_heading, 0

    # Flush remaining
    if buf_lines:
        if buf_tokens < min_tokens and chunks:
            # Merge with previous chunk
            prev = chunks[-1]
            merged = prev["content"] + "\n" + "\n".join(buf_lines)
            prev["content"] = merged
            prev["token_count"] = count_tokens(merged)
        else:
            chunks.append(_emit(buf_lines, buf_heading))

    # Re-number token_count with full content (including metadata prefix)
    for c in chunks:
        c["token_count"] = count_tokens(c["content"])

    return chunks


def _split_by_headings(content: str) -> List[Tuple[str, str]]:
    """Split by ## headings. Returns [(heading, body), ...]."""
    # Split on ## but not ###
    parts = re.split(r'^##\s+(.+)$', content, flags=re.MULTILINE)
    if len(parts) == 1:
        return [("", parts[0])]

    sections: List[Tuple[str, str]] = []
    # First element before any ## heading → no heading
    intro = parts[0].strip()
    if intro:
        sections.append(("", intro))
    for i in range(1, len(parts), 2):
        heading = parts[i].strip() if i < len(parts) else ""
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append((heading, body))
    return sections


def _split_by_sub_headings(content: str) -> List[Tuple[str, str]]:
    """Split by ### headings."""
    parts = re.split(r'^###\s+(.+)$', content, flags=re.MULTILINE)
    if len(parts) == 1:
        return []
    sections: List[Tuple[str, str]] = []
    for i in range(1, len(parts), 2):
        heading = parts[i].strip() if i < len(parts) else ""
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if body:
            sections.append((heading, body))
    return sections


# ── meeting: paragraph aggregation ───────────────────────────────

def chunk_meeting(
    content: str,
    title: str,
    *,
    target_tokens: int = 500,
    min_tokens: int = 200,
    max_tokens: int = 800,
) -> List[Dict[str, Any]]:
    """Aggregate paragraphs until reaching target token count."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: List[Dict[str, Any]] = []
    buf: List[str] = []
    buf_tokens: int = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if buf_tokens + para_tokens <= target_tokens or buf_tokens < min_tokens:
            buf.append(para)
            buf_tokens += para_tokens
        else:
            text = "\n\n".join(buf)
            chunks.append({
                "content": f"[来源: {title}]\n\n{text}",
                "token_count": count_tokens(text),
                "heading": "",
            })
            buf = [para]
            buf_tokens = para_tokens

    if buf:
        text = "\n\n".join(buf)
        chunks.append({
            "content": f"[来源: {title}]\n\n{text}",
            "token_count": count_tokens(text),
            "heading": "",
        })

    return chunks


# ── table: sparse wide-table → row-level extraction ─────────────

def chunk_table(
    content: str,
    title: str,
    *,
    target_tokens: int = 600,
) -> List[Dict[str, Any]]:
    """Parse a markdown table, extract non-empty cells, and group into compact chunks.

    For wide sparse tables (e.g. Roadmap with 26 columns), each meaningful
    row is compressed to "col: val | col: val" format, discarding empty cells.
    """
    lines = content.strip().split("\n")

    # Find header and separator
    header_idx = -1
    sep_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and not re.match(r'^\|\s*:?---', stripped):
            if header_idx < 0:
                header_idx = i
            elif sep_idx >= 0:
                break
        elif re.match(r'^\|\s*:?---', stripped):
            sep_idx = i

    if header_idx < 0:
        # No table structure detected, fall back to text chunking
        return chunk_text(content, title)

    headers = _parse_row(lines[header_idx])

    # Detect merged title row (single cell spanning all columns).
    # In non-standard tables, the separator may come after the title,
    # with real column headers in the next row.
    first_filled = sum(1 for c in headers if c.strip())
    if first_filled == 1 and sep_idx >= 0:
        # Look for real headers after the separator
        for i in range(sep_idx + 1, len(lines)):
            line = lines[i].strip()
            if not line.startswith("|"):
                continue
            if re.match(r'^\|\s*:?---', line):
                continue
            candidate = _parse_row(line)
            candidate_filled = sum(1 for c in candidate if c.strip())
            if candidate_filled > 1:
                headers = candidate
                header_idx = i
                break

    # Extract data rows (skip headers & separator, skip empty rows)
    rows: List[List[str]] = []
    data_start = max(sep_idx, header_idx) + 1
    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line.startswith("|"):
            continue
        cells = _parse_row(line)
        # Skip entirely empty rows
        if not any(c.strip() for c in cells):
            continue
        rows.append(cells)

    if not rows:
        return [{
            "content": f"[来源: {title}]\n\n{content}",
            "token_count": count_tokens(content),
            "heading": "",
        }]

    # Build compact rows: "col: val" for non-empty cells only
    compact_rows: List[str] = []
    for cells in rows:
        parts = []
        for j, cell in enumerate(cells):
            cell = cell.strip()
            if not cell:
                continue
            # Use header if available, otherwise just the value
            if j < len(headers) and headers[j].strip():
                parts.append(f"{headers[j].strip()}: {cell}")
            else:
                parts.append(cell)
        if parts:
            compact_rows.append(" | ".join(parts))

    # Group compact rows
    chunks: List[Dict[str, Any]] = []
    buf: List[str] = []
    buf_tokens: int = 0

    for row in compact_rows:
        rt = count_tokens(row)
        if buf_tokens + rt > target_tokens and buf:
            text = "\n".join(buf)
            chunks.append({
                "content": f"[来源: {title}]\n\n{text}",
                "token_count": count_tokens(text),
                "heading": "",
            })
            buf, buf_tokens = [], 0
        buf.append(row)
        buf_tokens += rt

    if buf:
        text = "\n".join(buf)
        chunks.append({
            "content": f"[来源: {title}]\n\n{text}",
            "token_count": count_tokens(text),
            "heading": "",
        })

    return chunks


def _parse_row(line: str) -> List[str]:
    """Parse a markdown table row into cell values."""
    # Remove leading/trailing pipes and split
    stripped = line.strip().strip("|")
    return [c.strip() for c in stripped.split("|")]


# ── text: fixed sliding window ───────────────────────────────────

def chunk_text(
    content: str,
    title: str,
    *,
    target_tokens: int = 800,
    min_tokens: int = 100,
    max_tokens: int = 1200,
    overlap_tokens: int = 150,
) -> List[Dict[str, Any]]:
    """Fixed sliding window with overlap."""
    windows = _fixed_window(content, target_tokens, min_tokens, max_tokens)
    chunks: List[Dict[str, Any]] = []
    for i, win in enumerate(windows):
        # Add overlap from previous window
        if i > 0 and overlap_tokens > 0:
            prev = windows[i - 1]
            if count_tokens(prev) > overlap_tokens:
                overlap = _tail_tokens(prev, overlap_tokens)
                win = overlap + "\n" + win
        chunks.append({
            "content": f"[来源: {title}]\n\n{win}",
            "token_count": count_tokens(win),
            "heading": "",
        })
    return chunks


def _fixed_window(
    text: str,
    target_tokens: int = 800,
    min_tokens: int = 100,
    max_tokens: int = 1200,
) -> List[str]:
    """Split text into fixed-token windows, respecting paragraph boundaries."""
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
            # Flush buffer
            if buf:
                windows.append("\n\n".join(buf))
                buf, buf_tokens = [], 0
            # Single huge paragraph → split by sentences first, then by lines
            sentences = re.split(r'(?<=[。！？.!?])\s*', para)
            if len(sentences) <= 1:
                # No sentence boundaries found → split by newlines (e.g. table rows)
                lines = para.split("\n")
                sub_buf, sub_tokens = [], 0
                for line in lines:
                    lt = count_tokens(line)
                    if sub_tokens + lt > target_tokens and sub_tokens >= min_tokens:
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
                    if sub_tokens + st > target_tokens and sub_tokens >= min_tokens:
                        windows.append(" ".join(sub_buf))
                        sub_buf, sub_tokens = [], 0
                    sub_buf.append(sent)
                    sub_tokens += st
                if sub_buf:
                    windows.append(" ".join(sub_buf))
        elif buf_tokens + para_tokens <= target_tokens or buf_tokens < min_tokens:
            buf.append(para)
            buf_tokens += para_tokens
        else:
            windows.append("\n\n".join(buf))
            buf, buf_tokens = [para], para_tokens

    if buf:
        windows.append("\n\n".join(buf))
    return windows


def _tail_tokens(text: str, n_tokens: int) -> str:
    """Return the last ~n_tokens tokens from text."""
    lines = text.split("\n")
    tail: List[str] = []
    tail_count = 0
    for line in reversed(lines):
        lt = count_tokens(line)
        if tail_count + lt > n_tokens * 2:  # generous buffer
            break
        tail.insert(0, line)
        tail_count += lt
    return "\n".join(tail)


# ── public API ────────────────────────────────────────────────────

def chunk_document(
    doc_id: str,
    title: str,
    content: str,
    node_type: str = "FILE",
) -> List[Dict[str, Any]]:
    """Chunk a single document. Returns list of chunk dicts ready for insert."""
    if not content or not content.strip():
        return []

    doc_type = classify_document(title, node_type, content)

    if doc_type == "structured":
        chunks = chunk_structured(content, title)
    elif doc_type == "meeting":
        chunks = chunk_meeting(content, title)
    elif doc_type == "table":
        chunks = chunk_table(content, title)
    else:
        chunks = chunk_text(content, title)

    # Assign chunk_index
    for i, c in enumerate(chunks):
        c["doc_id"] = doc_id
        c["chunk_index"] = i

    return chunks
