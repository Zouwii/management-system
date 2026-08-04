"""Markdown 清洗层 — 将钉钉导出的混合格式 MD 转为标准干净 Markdown。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# ── 人员提取 ──────────────────────────────────────────────

_PERSON_RE = re.compile(r'@([^\s@，,。；;、（）\(\)　]+)')

def extract_persons(text: str) -> List[str]:
    return list(dict.fromkeys(_PERSON_RE.findall(text)))


# ── HTML 清洗 ──────────────────────────────────────────────

def _clean_html_inline(text: str) -> str:
    """内联 HTML 清洗。注意：<br> 不转换行，用紧凑分隔符保留表格结构。"""
    # <br> → " / "（保留单行，不破坏表格）
    text = re.sub(r'<br\s*/?>', ' / ', text, flags=re.IGNORECASE)
    # <span ...>text</span> → text
    text = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', text, flags=re.IGNORECASE)
    # <strong>/<b>/<em>/<i> 标签
    text = re.sub(r'</?(?:strong|b|em|i)\s*>', '', text, flags=re.IGNORECASE)
    return text


def _convert_html_list(html_block: str) -> str:
    lines = []
    for raw in re.findall(r'<li([^>]*)>(.*?)</li>', html_block, re.IGNORECASE | re.DOTALL):
        attrs, content = raw[0], raw[1].strip()
        content = _clean_html_inline(content)
        indent = 0
        m = re.search(r'margin-left:\s*(\d+)\s*em', attrs)
        if m:
            indent = int(m.group(1))
        prefix = "  " * indent + "- "
        lines.append(prefix + content)
    return '\n'.join(lines)


def clean_html_blocks(text: str) -> str:
    text = re.sub(
        r'(<li[^>]*>.*?</li>\s*)+',
        lambda m: _convert_html_list(m.group(0)),
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r'</?(?:ul|ol|div|p|section|article)\s*>', '', text, flags=re.IGNORECASE)
    return text


# ── ::: 分隔符 ────────────────────────────────────────────

def clean_separators(text: str) -> str:
    text = re.sub(r'^:::\s*$', '\n<!-- segment -->\n', text, flags=re.MULTILINE)
    return text


# ── 粗体/删除线/转义 ──────────────────────────────────────

def clean_inline_format(text: str) -> str:

    # 标题行中的 **text** → text
    def _strip_bold(m):
        return re.sub(r'\*\*(.+?)\*\*', r'\1', m.group(0))

    text = re.sub(r'^(#{1,3})\s+(.+)', _strip_bold, text, flags=re.MULTILINE)

    # 表格行中的 **text** → text（修复后单行管道完整，能匹配了）
    text = re.sub(r'^\|.+\|$', _strip_bold, text, flags=re.MULTILINE)

    # 独立粗体行
    text = re.sub(
        r'^(\*\*.+?\*\*)\s*$',
        lambda m: re.sub(r'\*\*', '', m.group(1)),
        text,
        flags=re.MULTILINE,
    )

    # ~~删除线~~ → 保留内容
    text = re.sub(r'~~(.+?)~~', r'\1', text)

    # 转义字符
    text = text.replace('\\{', '{').replace('\\}', '}')

    # ☐ ☑ → [ ] [x]
    text = text.replace('☐', '[ ]').replace('☑', '[x]')

    return text


# ── 链接清洗 ──────────────────────────────────────────────

def clean_links(text: str) -> str:
    text = re.sub(
        r'\[(.*?)\]\(https?://file\+\.vscode-resource[^)]*\)',
        r'\1',
        text,
    )
    return text


# ── 图片 alt 优化 ─────────────────────────────────────────

def clean_images(text: str) -> str:
    def _fix_alt(m):
        alt, url, title = m.group(1), m.group(2), m.group(3) or ""
        alt_lower = alt.strip().lower()
        if (not alt or alt_lower in ('image.png', 'image', '图片', 'img')
                or re.match(r'^[a-f0-9]{32,}\.png$', alt_lower)):
            alt = "[配图]"
        if title:
            return f'![{alt}]({url} "{title}")'
        return f'![{alt}]({url})'

    return re.sub(r'!\[(.*?)\]\(([^)]+)\)(?:\s*"([^"]*)")?', _fix_alt, text)


# ── 代码块穿透 ────────────────────────────────────────────

def unwrap_inner_markdown(text: str) -> str:
    def _unwrap(m):
        lang = (m.group(1) or "").strip().lower()
        content = m.group(2)
        if lang == 'markdown':
            return '\n' + content + '\n'
        return m.group(0)
    return re.sub(r'```(\w*)\n(.*?)```', _unwrap, text, flags=re.DOTALL)


# ── 主入口 ────────────────────────────────────────────────

@dataclass
class CleanResult:
    cleaned_md: str
    persons: List[str] = field(default_factory=list)
    has_images: bool = False
    image_urls: List[str] = field(default_factory=list)
    deprecated_blocks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def clean_markdown(raw_md: str, doc_title: str = "") -> CleanResult:
    md = raw_md

    # 1. HTML <li> 块 → Markdown 列表
    md = clean_html_blocks(md)

    # 2. ::: 分隔符
    md = clean_separators(md)

    # 3. 内联 HTML
    md = _clean_html_inline(md)

    # 4. 链接清洗
    md = clean_links(md)

    # 5. 粗体/删除线/转义
    md = clean_inline_format(md)

    # 6. 清除残留 :::
    md = re.sub(r':::\s*$', '', md, flags=re.MULTILINE)
    md = re.sub(r'([^\n]):::', r'\1', md)

    # 7. 代码块穿透
    md = unwrap_inner_markdown(md)

    # 8. 图片 alt
    md = clean_images(md)

    # 9. 提取元数据
    deprecated = re.findall(r'~~(.+?)~~', raw_md)
    image_urls = re.findall(r'!\[.*?\]\(([^)]+)\)', md)
    persons = extract_persons(md)

    return CleanResult(
        cleaned_md=md.strip(),
        persons=persons,
        has_images=bool(image_urls),
        image_urls=image_urls,
        deprecated_blocks=deprecated,
        warnings=[],
    )
