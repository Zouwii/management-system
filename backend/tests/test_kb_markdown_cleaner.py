"""Regression tests for the conservative Markdown cleaner."""

from __future__ import annotations

import unittest

from ai.knowledge.v2.cleaner import clean_markdown


class MarkdownCleanerTests(unittest.TestCase):
    def test_image_keeps_only_name(self):
        result = clean_markdown(
            "![image.png](https://example.com/img/"
            'ffbe80c6-ae7c-4745-a476-b151b97364b8.png?token=secret "")'
        )

        self.assertEqual(
            result.cleaned_md,
            "【图片：ffbe80c6-ae7c-4745-a476-b151b97364b8.png】",
        )
        self.assertNotIn("https://", result.cleaned_md)
        self.assertEqual(result.stats["image_count"], 1)

    def test_table_br_is_preserved_but_body_br_becomes_newline(self):
        source = "正文一<br/>正文二\n\n| 字段 | 说明 |\n|---|---|\n| A | 第一项<br/>第二项 |"

        result = clean_markdown(source)

        self.assertIn("正文一\n正文二", result.cleaned_md)
        self.assertIn("| A | 第一项<br>第二项 |", result.cleaned_md)

    def test_block_html_boundaries_are_preserved(self):
        source = (
            "<div>第一段</div><div>第二段</div>\n\n"
            "| 字段 | 说明 |\n|---|---|\n"
            "| A | <div>第一项</div><div>第二项</div> |"
        )

        result = clean_markdown(source)

        self.assertIn("第一段\n第二段", result.cleaned_md)
        self.assertIn("| A | 第一项<br>第二项 |", result.cleaned_md)
        self.assertNotIn("第一段第二段", result.cleaned_md)

    def test_adjacent_emphasis_runs_are_separated(self):
        source = "**扣分规则**<span></span>**特殊情况**"

        result = clean_markdown(source)

        self.assertEqual(result.cleaned_md, "**扣分规则** **特殊情况**")
        self.assertNotIn("****", result.cleaned_md)

    def test_deprecated_content_and_adjacent_span_boundary_are_preserved(self):
        source = (
            '<span style="color:red">~~尾板高度~~</span>'
            '<span style="color:red">Bit2 驻车反馈</span>'
        )

        result = clean_markdown(source)

        self.assertEqual(result.cleaned_md, "~~尾板高度~~ Bit2 驻车反馈")
        self.assertEqual(result.deprecated_blocks, ["尾板高度"])

    def test_multiline_html_list_becomes_markdown(self):
        source = (
            "标题<li>第一项\n补充</li>"
            '<li style="margin-left:1em">第二项</li>正文'
        )

        result = clean_markdown(source)

        self.assertIn("标题\n- 第一项\n补充\n  - 第二项\n正文", result.cleaned_md)
        self.assertNotIn("<li", result.cleaned_md)

    def test_code_block_is_not_cleaned(self):
        source = "正文<span>内容</span>\n\n```html\n<span>代码</span>\n```"

        result = clean_markdown(source)

        self.assertIn("正文内容", result.cleaned_md)
        self.assertIn("```html\n<span>代码</span>\n```", result.cleaned_md)
        self.assertEqual(result.warnings, [])

    def test_html_code_superscript_and_escaped_placeholder(self):
        source = (
            "| 示例 | <pre><code>{<br>\"ok\": true<br>}</code></pre> |\n"
            "单位：m/s<sup>2</sup>；路径：jzhw/laser/\\<index\\>"
        )

        result = clean_markdown(source)

        self.assertIn('| 示例 | {<br>"ok": true<br>} |', result.cleaned_md)
        self.assertIn("单位：m/s^2；路径：jzhw/laser/\\<index\\>", result.cleaned_md)
        self.assertEqual(result.warnings, [])

    def test_export_noise_is_removed(self):
        source = "::: \n标题\n::: \n[]\n[]正文\n1.\n有效内容"

        result = clean_markdown(source)

        self.assertEqual(result.cleaned_md, "标题\n\n正文\n\n有效内容")

    def test_cleaning_is_idempotent(self):
        source = (
            "# **标题**\n\n"
            '<span style="color:red">内容</span><span>Bit2</span>\n\n'
            "| 字段 | 说明 |\n|---|---|\n| A | 一<br/>二 |\n\n"
            "![image.png](https://example.com/image.png?long=query)"
        )
        first = clean_markdown(source).cleaned_md
        second = clean_markdown(first).cleaned_md

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
