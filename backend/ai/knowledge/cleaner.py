"""Markdown 清洗层：将钉钉导出的混合 Markdown/HTML 规范化。

清洗后的 Markdown 会成为 ``kb_documents.content`` 中的知识库原文，因此
本模块只做可确定的格式规范化，不推断业务语义，也不执行检索切分。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from urllib.parse import unquote, urlparse


_PERSON_RE = re.compile(r"@([^\s@，,。；;、（）\(\)　]+)")
_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^\s\)]+))"
    r"(?:\s+[\"'].*?[\"'])?\s*\)"
)
_HTML_LIST_RE = re.compile(
    r"(?:<li\b[^>]*>.*?</li>\s*)+", re.IGNORECASE | re.DOTALL
)
_HTML_TAG_RE = re.compile(r"(?<!\\)</?([A-Za-z][\w:-]*)\b[^>]*>")
_EMPTY_NUMBER_RE = re.compile(
    r"^\s*(?:\d+[.)、]|[一二三四五六七八九十]+[、.)])\s*$"
)
_CODE_PLACEHOLDER = "@@RAG_V2_CODE_BLOCK_{}@@"


def extract_persons(text: str) -> List[str]:
    return list(dict.fromkeys(_PERSON_RE.findall(text)))


def _normalize_basic(text: str) -> str:
    return (
        text.lstrip("\ufeff")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u00a0", " ")
    )


def _protect_fenced_code(text: str) -> Tuple[str, List[str], List[str]]:
    """Protect fenced code blocks from all later cleaning operations."""
    lines = text.splitlines(keepends=True)
    blocks: List[str] = []
    output: List[str] = []
    warnings: List[str] = []
    current: List[str] = []
    fence_char = ""
    fence_len = 0

    for line in lines:
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if not current:
            if fence:
                marker = fence.group(1)
                fence_char = marker[0]
                fence_len = len(marker)
                current = [line]
            else:
                output.append(line)
            continue

        current.append(line)
        closing = re.match(
            rf"{re.escape(fence_char)}{{{fence_len},}}\s*$", stripped
        )
        if closing:
            index = len(blocks)
            blocks.append("".join(current).rstrip("\n"))
            output.append(_CODE_PLACEHOLDER.format(index) + "\n")
            current = []
            fence_char = ""
            fence_len = 0

    if current:
        # Keep malformed input losslessly. A warning lets the ingestion layer
        # decide whether this document is safe to overwrite.
        warnings.append("UNCLOSED_CODE_FENCE")
        output.extend(current)

    return "".join(output), blocks, warnings


def _restore_fenced_code(text: str, blocks: List[str]) -> str:
    for index, block in enumerate(blocks):
        text = text.replace(_CODE_PLACEHOLDER.format(index), block)
    return text


def _clean_inline_for_list(text: str) -> str:
    text = re.sub(r"</span>\s*<span\b[^>]*>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?span\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?u\b[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"</?(?:strong|b|em|i)\b[^>]*>", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"<br\s*/?>", "<br>", text, flags=re.IGNORECASE)
    return text.strip()


def _convert_list_run(match: re.Match[str], *, in_table: bool) -> str:
    items: List[str] = []
    for item in re.finditer(
        r"<li\b([^>]*)>(.*?)</li>",
        match.group(0),
        flags=re.IGNORECASE | re.DOTALL,
    ):
        attrs, content = item.group(1), _clean_inline_for_list(item.group(2))
        indent_match = re.search(r"margin-left:\s*(\d+)\s*em", attrs)
        indent = int(indent_match.group(1)) if indent_match else 0
        if in_table:
            bullet = "•" if indent == 0 else "◦"
            items.append(f"{'　' * indent}{bullet} {content}")
        else:
            items.append(f"{'  ' * indent}- {content}")
    return "<br>".join(items) if in_table else "\n".join(items)


def _convert_html_lists(text: str) -> str:
    # Convert table-contained lists first because a literal newline would end
    # the Markdown row. All remaining list runs may safely span source lines.
    output: List[str] = []
    for line in text.split("\n"):
        in_table = line.lstrip().startswith("|")
        if in_table:
            line = _HTML_LIST_RE.sub(
                lambda match: _convert_list_run(match, in_table=True), line
            )
        output.append(line)
    text = "\n".join(output)
    text = _HTML_LIST_RE.sub(
        lambda match: "\n" + _convert_list_run(match, in_table=False) + "\n",
        text,
    )
    # The exporter sometimes emits ul/ol wrappers and sometimes bare li runs.
    return re.sub(r"</?(?:ul|ol)\b[^>]*>", "", text, flags=re.IGNORECASE)


def _image_name(alt: str, url: str) -> str:
    path = unquote(urlparse(url).path)
    url_name = path.rsplit("/", 1)[-1].strip()
    if url_name:
        return url_name
    return alt.strip()


def _replace_images(text: str) -> Tuple[str, List[str]]:
    urls: List[str] = []

    def replace(match: re.Match[str]) -> str:
        url = (match.group(2) or match.group(3) or "").strip()
        urls.append(url)
        name = _image_name(match.group(1), url)
        return f"【图片：{name}】" if name else "【图片】"

    return _IMAGE_RE.sub(replace, text), urls


def _normalize_adjacent_emphasis(text: str) -> str:
    """Keep neighboring Markdown emphasis runs syntactically separate.

    Removing inline HTML can expose runs such as ``**A****B**``.  Markdown
    parsers disagree on that spelling, and it also makes the visible text
    harder to read.  Insert one separator while preserving both emphasis
    spans.  Fenced code is protected before this function is called.
    """
    previous = None
    while previous != text:
        previous = text
        # Four stars are the unambiguous boundary between two bold runs;
        # handling this first also covers a run whose text ends in punctuation.
        text = text.replace("****", "** **")
        text = re.sub(
            r"\*\*([^*\n]+)\*\*\s*\*\*([^*\n]+)\*\*",
            r"**\1** **\2**",
            text,
        )
        text = re.sub(
            r"(?<!\*)\*([^*\n]+)\*(?!\*)\s+\*([^*\n]+)\*(?!\*)",
            r"*\1* *\2*",
            text,
        )
    return text


def _clean_inline_html(line: str, *, in_table: bool) -> str:
    # Keep an explicit boundary between adjacent styled runs. Without it,
    # values such as "上高压" + "Bit2" become an incorrect single token.
    line = re.sub(
        r"</span>\s*<span\b[^>]*>", " ", line, flags=re.IGNORECASE
    )
    line = re.sub(r"</?span\b[^>]*>", "", line, flags=re.IGNORECASE)
    line = re.sub(r"</?u\b[^>]*>", "", line, flags=re.IGNORECASE)
    line = re.sub(r"</?font\b[^>]*>", "", line, flags=re.IGNORECASE)
    line = re.sub(
        r"</?(?:strong|b|em|i)\b[^>]*>", "", line, flags=re.IGNORECASE
    )
    # Block containers are layout wrappers, but their boundaries are useful
    # document structure. Preserve them as a body newline or a table-safe
    # ``<br>`` instead of concatenating adjacent blocks.
    block_separator = "<br>" if in_table else "\n"
    line = re.sub(
        r"</?(?:div|p|section|article)\b[^>]*>",
        block_separator,
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(
        r"<sup\b[^>]*>(.*?)</sup>",
        lambda match: _script_text(match.group(1), "^"),
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(
        r"<sub\b[^>]*>(.*?)</sub>",
        lambda match: _script_text(match.group(1), "_"),
        line,
        flags=re.IGNORECASE,
    )
    # Exported API tables sometimes use pre/code solely as visual containers
    # inside cells. Keep their visible JSON/text and let the table-aware parser
    # decide how to represent it later.
    line = re.sub(r"</?(?:pre|code)\b[^>]*>", "", line, flags=re.IGNORECASE)

    if in_table:
        line = re.sub(r"<br\s*/?>", "<br>", line, flags=re.IGNORECASE)
        line = re.sub(r"(?:<br>\s*){2,}", "<br>", line)
        line = re.sub(r"(\|\s*)<br>", r"\1", line)
        line = re.sub(r"<br>(\s*\|)", r"\1", line)
    else:
        line = re.sub(r"<br\s*/?>", "\n", line, flags=re.IGNORECASE)
        line = re.sub(r"\n{2,}", "\n", line)
    return line


def _script_text(content: str, marker: str) -> str:
    content = content.strip()
    if len(content) <= 1 or re.fullmatch(r"[A-Za-z0-9+-]+", content):
        return marker + content
    return f"{marker}({content})"


def _normalize_heading(line: str) -> str:
    match = re.match(r"^(\s*#{1,6}\s+)\*\*(.*?)\*\*\s*$", line)
    if match:
        return f"{match.group(1)}{match.group(2).strip()}"
    return line


def _clean_lines(text: str) -> str:
    output: List[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped == ":::" or stripped == "[]" or _EMPTY_NUMBER_RE.match(line):
            output.append("")
            continue

        # ``[]正文`` is another exporter artifact seen in the corpus. It is
        # not valid Markdown checkbox syntax (which would be ``[ ]``).
        line = re.sub(r"^\s*\[\](?=\S)", "", line)

        in_table = line.lstrip().startswith("|")
        line = _clean_inline_html(line, in_table=in_table)
        line = _normalize_adjacent_emphasis(line)
        line = _normalize_heading(line)
        output.extend(part.rstrip() for part in line.split("\n"))

    # At most one empty line between blocks. This produces two newline
    # characters while keeping the Markdown compact and readable.
    compact: List[str] = []
    previous_empty = False
    for line in output:
        empty = not line.strip()
        if empty and previous_empty:
            continue
        compact.append(line)
        previous_empty = empty
    return "\n".join(compact).strip()


def _unknown_html_tags(text: str) -> List[str]:
    known = {
        "br",
        "span",
        "u",
        "font",
        "div",
        "p",
        "section",
        "article",
        "ul",
        "ol",
        "li",
        "strong",
        "b",
        "em",
        "i",
        "pre",
        "code",
        "sup",
        "sub",
    }
    return sorted(
        {
            match.group(1).lower()
            for match in _HTML_TAG_RE.finditer(text)
            if match.group(1).lower() not in known
        }
    )


@dataclass
class CleanResult:
    cleaned_md: str
    persons: List[str] = field(default_factory=list)
    has_images: bool = False
    image_urls: List[str] = field(default_factory=list)
    deprecated_blocks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


def clean_markdown(raw_md: str, doc_title: str = "") -> CleanResult:
    """Return deterministic, retrieval-safe Markdown without chunking it."""
    del doc_title  # Reserved for future validation; no semantic rewriting here.

    normalized = _normalize_basic(raw_md or "")
    protected, code_blocks, warnings = _protect_fenced_code(normalized)
    protected = _convert_html_lists(protected)
    protected, image_urls = _replace_images(protected)
    cleaned = _clean_lines(protected)
    unknown_tags = _unknown_html_tags(cleaned)
    cleaned = _restore_fenced_code(cleaned, code_blocks).strip()

    warnings.extend(f"UNKNOWN_HTML_TAG:{tag}" for tag in unknown_tags)

    deprecated = re.findall(r"~~(.+?)~~", normalized, flags=re.DOTALL)
    stats = {
        "input_chars": len(normalized),
        "output_chars": len(cleaned),
        "heading_count": len(re.findall(r"^#{1,6}\s+", cleaned, re.MULTILINE)),
        "table_line_count": len(
            [line for line in cleaned.splitlines() if line.lstrip().startswith("|")]
        ),
        "code_block_count": len(code_blocks),
        "image_count": len(image_urls),
        "deprecated_count": len(deprecated),
        "unknown_html_tag_count": len(unknown_tags),
    }

    return CleanResult(
        cleaned_md=cleaned,
        persons=extract_persons(cleaned),
        has_images=bool(image_urls),
        image_urls=image_urls,
        deprecated_blocks=deprecated,
        warnings=warnings,
        stats=stats,
    )
