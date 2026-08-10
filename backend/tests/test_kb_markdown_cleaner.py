"""Regression tests for the conservative Markdown cleaner."""

from __future__ import annotations

import unittest

from ai.knowledge.cleaner import clean_markdown


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

    def test_adjacent_spans_join_identifiers_but_separate_phrases(self):
        result = clean_markdown(
            "<span>p</span><span>rotoc</span> "
            "<span>insta</span><span>nt</span> "
            "<span>energy</span><span>Mode</span> "
            "<span>上高压</span><span>Bit2 驻车反馈</span>"
        )
        self.assertIn("protoc instant energyMode", result.cleaned_md)
        self.assertIn("上高压 Bit2 驻车反馈", result.cleaned_md)

    def test_dingtalk_node_image_syntax_is_document_link(self):
        result = clean_markdown(
            "![tb迁移](https://alidocs.dingtalk.com/i/nodes/abc123)"
        )
        self.assertEqual(
            result.cleaned_md,
            "[tb迁移](https://alidocs.dingtalk.com/i/nodes/abc123)",
        )
        self.assertEqual(result.stats["document_link_count"], 1)
        self.assertEqual(result.stats["image_count"], 0)

    def test_unknown_media_is_preserved_with_warning(self):
        source = "![业务标题](https://example.com/media/no-extension)"
        result = clean_markdown(source)
        self.assertEqual(result.cleaned_md, source)
        self.assertIn("UNKNOWN_MEDIA_URL", result.warnings)

    def test_whole_document_escaped_structure_is_restored(self):
        result = clean_markdown(
            "\\# 标题\n\\## 结论\n\\| 字段 \\| 内容 \\|\n\\|---\\|---\\|"
        )
        self.assertIn("# 标题", result.cleaned_md)
        self.assertIn("## 结论", result.cleaned_md)
        self.assertIn("| 字段 | 内容 |", result.cleaned_md)
        self.assertGreater(result.stats["escaped_heading_restored_count"], 0)
        self.assertGreater(result.stats["escaped_table_restored_count"], 0)

    def test_local_escapes_and_code_are_untouched(self):
        source = (
            "Shell: echo a\\|b\n"
            "Regex: \\#tag\n\n"
            "```text\n\\# literal\n\\| pipe\n\u00a0indent\n```"
        )
        result = clean_markdown(source)
        self.assertIn("echo a\\|b", result.cleaned_md)
        self.assertIn("Regex: \\#tag", result.cleaned_md)
        self.assertIn("```text\n\\# literal\n\\| pipe\n\u00a0indent\n```", result.cleaned_md)

    def test_unclosed_code_fence_is_lossless_and_warns(self):
        source = "```json\n{\u00a0\"x\": true}"
        result = clean_markdown(source)
        self.assertEqual(result.cleaned_md, source)
        self.assertIn("UNCLOSED_CODE_FENCE", result.warnings)

    def test_required_stats_are_stable(self):
        result = clean_markdown("# 标题\n\n![x](https://example.com/x.png)")
        required = {
            "input_chars", "output_chars", "heading_count", "table_line_count",
            "code_block_count", "image_count", "document_link_count",
            "unknown_media_count", "escaped_heading_restored_count",
            "escaped_table_restored_count", "span_join_count", "span_space_count",
            "warning_count",
        }
        self.assertTrue(required.issubset(result.stats))
        self.assertEqual(result.stats, clean_markdown("# 标题\n\n![x](https://example.com/x.png)").stats)

    def test_adjacent_span_joins_identifier_punctuation(self):
        """protoc. and foo::bar join correctly while CJK boundaries keep space."""
        result = clean_markdown(
            "<span>protoc</span><span>.</span> "
            "<span>foo</span><span>::</span><span>bar</span> "
            "<span>上高压</span><span>Bit2</span>"
        )
        self.assertIn("protoc. foo::bar 上高压 Bit2", result.cleaned_md)

    def test_dingtalk_hostname_rejects_suffix_confusion(self):
        """evildingtalk.com must not be recognised as a DingTalk node."""
        result = clean_markdown(
            "![malicious](https://evildingtalk.com/i/nodes/abc123)"
        )
        # Not a DingTalk node → unknown media (no image extension)
        self.assertIn("UNKNOWN_MEDIA_URL", result.warnings)
        self.assertEqual(result.stats["document_link_count"], 0)

    def test_teambition_doc_is_document_link(self):
        """Teambition workspace docs are links, not images."""
        result = clean_markdown(
            "![需求文档](https://thoughts.teambition.com/workspaces/123/docs/456)"
        )
        self.assertEqual(
            result.cleaned_md,
            "[需求文档](https://thoughts.teambition.com/workspaces/123/docs/456)",
        )
        self.assertEqual(result.stats["document_link_count"], 1)
        self.assertEqual(result.stats["image_count"], 0)

    def test_span_stats_reflect_output_decisions(self):
        """span_join_count and span_space_count count actual output decisions."""
        result = clean_markdown(
            "<span>protoc</span><span>.</span> "
            "<span>上高压</span><span>Bit2</span>"
        )
        # Boundaries: protoc-. (join), .-上高压 (space via gap), 上高压-Bit2 (space)
        self.assertEqual(result.stats["span_join_count"], 1)
        self.assertEqual(result.stats["span_space_count"], 2)

    def test_new_cases_are_idempotent(self):
        """Cleaned output from new cases is idempotent."""
        source = (
            "<span>protoc</span><span>.</span> "
            "<span>foo</span><span>::</span><span>bar</span> "
            "<span>上高压</span><span>Bit2</span>"
        )
        first = clean_markdown(source).cleaned_md
        second = clean_markdown(first).cleaned_md
        self.assertEqual(first, second)

        source2 = (
            "![doc](https://thoughts.teambition.com/workspaces/1/docs/2)"
        )
        first2 = clean_markdown(source2).cleaned_md
        second2 = clean_markdown(first2).cleaned_md
        self.assertEqual(first2, second2)


if __name__ == "__main__":
    unittest.main()
