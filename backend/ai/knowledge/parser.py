"""Document parser: DingTalk blocks / HTML / rich-text → Markdown.

Handles:
  - DingTalk blocks API response (list of {blockType, paragraph/heading/...})
  - HTML (regex-based fallback)
  - JSON block tree (alternative DingTalk doc format)
  - Plain text (passthrough)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


# ── DingTalk blocks → Markdown ─────────────────────────────────

def blocks_to_markdown(blocks: List[dict]) -> str:
    """Convert DingTalk doc blocks array to Markdown.

    Input: result.data from GET /v1.0/doc/suites/documents/<id>/blocks
    Each block: {blockType, paragraph/heading/orderedList/unorderedList/table/blockquote, index, id}
    """
    if not blocks:
        return ""

    lines: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bt = block.get("blockType", "")
        body = block.get(bt, {})

        if bt == "heading":
            level = (body.get("level") or "heading-2").replace("heading-", "")
            text = (body.get("text") or "").strip()
            if text:
                lines.append(f"\n{'#' * int(level)} {text}\n")
        elif bt == "paragraph":
            text = (body.get("text") or "").strip()
            if text:
                lines.append(text)
        elif bt == "unorderedList":
            text = (body.get("text") or "").strip()
            if text:
                lines.append(f"- {text}")
        elif bt == "orderedList":
            text = (body.get("text") or "").strip()
            if text:
                lines.append(f"1. {text}")
        elif bt == "blockquote":
            text = (body.get("text") or "").strip()
            if text:
                for line in text.split("\n"):
                    lines.append(f"> {line}")
        elif bt == "code":
            text = (body.get("text") or "").strip()
            lang = body.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif bt == "table":
            lines.append(_dingtalk_table_to_md(body))
        elif bt == "columns":
            # Recurse into children blocks inside columns
            inner = _convert_columns(body)
            if inner:
                lines.append(inner)
        elif bt == "attachment":
            name = (body.get("name") or "").strip()
            if name:
                lines.append(f"[附件: {name}]")
        elif bt == "unknown":
            continue
        else:
            # fallback: try to get text from any known keys
            text = (
                body.get("text") or body.get("content") or ""
            )
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())

    result = "\n\n".join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def _dingtalk_table_to_md(body: dict) -> str:
    """Convert a DingTalk table block to markdown table.

    cells is a 2D array: cells[row][col].
    Dimensions come from rowSize/colSize (rowCount/colCount are null in API).
    """
    cells = body.get("cells") or []
    if not cells:
        return ""

    # Use rowSize/colSize; fall back to deriving from 2D array
    row_count = body.get("rowSize") or body.get("rowCount") or len(cells)
    if cells and isinstance(cells[0], list):
        col_count = body.get("colSize") or body.get("colCount") or len(cells[0])
    else:
        col_count = body.get("colSize") or body.get("colCount") or len(cells)

    lines: List[str] = []
    for r in range(row_count):
        if r >= len(cells):
            break
        row_cells: List[str] = []
        for c in range(col_count):
            cell = cells[r][c] if c < len(cells[r]) else ""
            if isinstance(cell, dict):
                cell_text = (cell.get("text") or cell.get("value") or "").strip()
            else:
                cell_text = str(cell)
            row_cells.append(cell_text)
        lines.append("| " + " | ".join(row_cells) + " |")
        if r == 0:
            lines.append("| " + " | ".join("---" for _ in range(col_count)) + " |")
    return "\n".join(lines)


def _convert_columns(body: dict) -> str:
    """Recurse into columns.children and convert nested blocks to markdown.

    columns.children is a list of columns; each column is a list of blocks.
    """
    children = body.get("children") or []
    if not children:
        return ""

    all_parts: List[str] = []
    for column_blocks in children:
        if not isinstance(column_blocks, list):
            continue
        # Recurse: use blocks_to_markdown on the column's block list
        inner = blocks_to_markdown(column_blocks)
        if inner:
            all_parts.append(inner)

    return "\n\n".join(all_parts)


# ── workbook → Markdown ────────────────────────────────────────

def workbook_to_markdown(sheets: List[dict]) -> str:
    """Convert workbook sheet data to Markdown tables.

    Input: sheets = [(sheet_name, rows_data), ...]
    where rows_data is a 2D array of values.
    """
    if not sheets:
        return ""

    parts: List[str] = []
    for sheet_name, rows in sheets:
        if not rows:
            continue
        parts.append(f"## {sheet_name}\n")
        headers = rows[0] if rows else []
        if headers:
            parts.append("| " + " | ".join(str(h) for h in headers) + " |")
            parts.append("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows[1:]:
            parts.append("| " + " | ".join(str(c) for c in row) + " |")
        parts.append("")

    return "\n".join(parts)


# ── HTML → Markdown ────────────────────────────────────────────

def html_to_markdown(html: str) -> str:
    """Convert HTML content to Markdown using regex and string transforms.

    Falls back gracefully: if we can't parse something, it stays as text.
    """
    if not html or not html.strip():
        return ""

    text = html.strip()

    # If it's a JSON block structure (DingTalk doc format), parse it
    if text.startswith("{"):
        try:
            import json
            data = json.loads(text)
            return _parse_block_tree(data)
        except (json.JSONDecodeError, ValueError):
            pass

    return _html_text_to_markdown(text)


def _parse_block_tree(data: dict) -> str:
    """Recursively convert a DingTalk doc block tree to Markdown."""
    blocks = data.get("blocks") or data.get("content") or []
    if isinstance(blocks, dict):
        blocks = [blocks]
    if not isinstance(blocks, list):
        return str(data)

    lines: List[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            lines.append(str(block))
            continue
        block_type = (block.get("type") or block.get("blockType") or "").lower()
        text = block.get("text") or block.get("content") or ""

        if isinstance(text, list):
            text = "".join(
                t.get("text") or t.get("content") or ""
                if isinstance(t, dict) else str(t)
                for t in text
            )

        elif block_type in ("heading1", "header1", "h1"):
            lines.append(f"\n# {text}\n")
        elif block_type in ("heading2", "header2", "h2"):
            lines.append(f"\n## {text}\n")
        elif block_type in ("heading3", "header3", "h3"):
            lines.append(f"\n### {text}\n")
        elif block_type in ("heading4", "header4", "h4"):
            lines.append(f"\n#### {text}\n")
        elif block_type in ("bullet_list", "unordered_list", "unorderedlist"):
            children = block.get("children") or block.get("blocks") or []
            for child in children:
                if isinstance(child, dict):
                    ct = child.get("text") or child.get("content") or ""
                    if isinstance(ct, list):
                        ct = "".join(
                            t.get("text") or t.get("content") or ""
                            if isinstance(t, dict) else str(t)
                            for t in ct
                        )
                    lines.append(f"- {ct}")
            continue
        elif block_type in ("ordered_list", "orderedlist"):
            children = block.get("children") or block.get("blocks") or []
            for idx, child in enumerate(children, 1):
                if isinstance(child, dict):
                    ct = child.get("text") or child.get("content") or ""
                    if isinstance(ct, list):
                        ct = "".join(
                            t.get("text") or t.get("content") or ""
                            if isinstance(t, dict) else str(t)
                            for t in ct
                        )
                    lines.append(f"{idx}. {ct}")
            continue
        elif block_type == "code":
            lang = block.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif block_type == "divider":
            lines.append("---")
        elif block_type == "image":
            alt = block.get("alt", "")
            src = block.get("url") or block.get("src", "")
            lines.append(f"![{alt}]({src})")
        elif block_type == "table":
            lines.append(_table_to_markdown(block))
        elif block_type == "quote":
            for line in text.split("\n"):
                lines.append(f"> {line}")
        else:
            children = block.get("children") or block.get("blocks") or []
            if children:
                inner = _parse_block_tree({"blocks": children})
                lines.append(inner)
            elif text:
                lines.append(text)

    result = "\n".join(lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def _html_text_to_markdown(html: str) -> str:
    """Convert raw HTML string to Markdown using regex transforms.

    This is a fallback when markdownify/bleach are not available.
    """
    text = html

    # Strip script and style blocks
    text = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Headings
    for i in range(6, 0, -1):
        text = re.sub(
            rf'<h{i}\b[^>]*>(.*?)</h{i}>',
            lambda m, level=i: f'\n\n{"#" * level} {_strip_tags(m.group(1)).strip()}\n\n',
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    # Bold / italic
    text = re.sub(r'<(strong|b)\b[^>]*>(.*?)</\1>', r'**\2**', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<(em|i)\b[^>]*>(.*?)</\1>', r'*\2*', text, flags=re.DOTALL | re.IGNORECASE)

    # Code blocks
    text = re.sub(r'<pre\b[^>]*><code\b[^>]*>(.*?)</code></pre>', r'```\n\1\n```', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<code\b[^>]*>(.*?)</code>', r'`\1`', text, flags=re.DOTALL | re.IGNORECASE)

    # Links
    text = re.sub(
        r'<a\b[^>]*href=["\'](.*?)["\'][^>]*>(.*?)</a>',
        r'[\2](\1)',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Images
    text = re.sub(
        r'<img\b[^>]*src=["\'](.*?)["\'][^>]*alt=["\'](.*?)["\'][^>]*/?>',
        r'![\2](\1)',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r'<img\b[^>]*src=["\'](.*?)["\'][^>]*/?>',
        r'![](\1)',
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # Lists
    text = re.sub(r'<li\b[^>]*>(.*?)</li>', r'- \1\n', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'</?[ou]l\b[^>]*>', '', text, flags=re.DOTALL | re.IGNORECASE)

    # Tables (basic)
    text = re.sub(r'</?table\b[^>]*>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'</?thead\b[^>]*>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'</?tbody\b[^>]*>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<tr\b[^>]*>(.*?)</tr>', _tr_to_markdown_row, text, flags=re.DOTALL | re.IGNORECASE)

    # Blockquotes
    text = re.sub(r'<blockquote\b[^>]*>(.*?)</blockquote>',
                  lambda m: '\n'.join(f'> {line}' for line in m.group(1).split('\n')),
                  text, flags=re.DOTALL | re.IGNORECASE)

    # Horizontal rule
    text = re.sub(r'<hr\b[^>]*/?>', '---', text, flags=re.DOTALL | re.IGNORECASE)

    # Paragraphs
    text = re.sub(r'<p\b[^>]*>(.*?)</p>', r'\1\n\n', text, flags=re.DOTALL | re.IGNORECASE)

    # Line breaks
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.DOTALL | re.IGNORECASE)

    # Strip remaining tags
    text = _strip_tags(text)

    # Clean up whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def _strip_tags(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text)


def _tr_to_markdown_row(match) -> str:
    cells = re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', match.group(1), flags=re.DOTALL | re.IGNORECASE)
    return '| ' + ' | '.join(_strip_tags(c).strip() for c in cells) + ' |'


def _table_to_markdown(block: dict) -> str:
    """Convert a block-tree table node to a markdown table."""
    rows = block.get("rows") or block.get("children") or []
    if not isinstance(rows, list):
        return ""
    lines: List[str] = []
    for i, row in enumerate(rows):
        cells = row.get("cells") or row.get("children") or []
        if isinstance(cells, list):
            cell_texts = []
            for c in cells:
                if isinstance(c, dict):
                    cell_texts.append(str(c.get("text") or c.get("content") or ""))
                else:
                    cell_texts.append(str(c))
            lines.append("| " + " | ".join(cell_texts) + " |")
        if i == 0:
            lines.append("| " + " | ".join("---" for _ in range(len(cells))) + " |")
    return "\n".join(lines)


# ── public API ──────────────────────────────────────────────────

def parse_document(raw_content: Any, content_type: str = "blocks") -> Dict[str, Any]:
    """Parse raw document content into clean Markdown.

    Args:
        raw_content: The raw document body from the DingTalk API.
            - content_type="blocks": list of DingTalk block dicts
            - content_type="html": HTML string
            - content_type="text": plain text string
            - content_type="workbook": list of (sheet_name, rows_2d)

    Returns:
        Dict with keys: markdown, format, parse_status
    """
    if content_type == "blocks":
        if not raw_content or not isinstance(raw_content, list):
            return {"markdown": "", "format": "blocks", "parse_status": "empty"}
        try:
            md = blocks_to_markdown(raw_content)
            return {"markdown": md, "format": "markdown", "parse_status": "ok"}
        except Exception:
            return {"markdown": "", "format": "blocks", "parse_status": "error"}

    if content_type == "workbook":
        if not raw_content:
            return {"markdown": "", "format": "workbook", "parse_status": "empty"}
        try:
            md = workbook_to_markdown(raw_content)
            return {"markdown": md, "format": "markdown", "parse_status": "ok"}
        except Exception:
            return {"markdown": "", "format": "workbook", "parse_status": "error"}

    raw_str = str(raw_content) if raw_content else ""
    if not raw_str.strip():
        return {"markdown": "", "format": content_type, "parse_status": "empty"}

    if content_type in ("text", "plain"):
        return {"markdown": raw_str.strip(), "format": "text", "parse_status": "passthrough"}

    try:
        md = html_to_markdown(raw_str)
        return {"markdown": md, "format": "markdown", "parse_status": "ok"}
    except Exception:
        return {"markdown": raw_str, "format": content_type, "parse_status": "raw"}
