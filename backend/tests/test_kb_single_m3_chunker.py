from __future__ import annotations

import json
import unittest

from ai.knowledge.single_m3_chunker import MAX_TOKENS, chunk_document_single_m3


class SingleM3ChunkerTests(unittest.TestCase):
    class CharTokenizer:
        def encode(self, text, add_special_tokens=True):
            return list(text) + (["<special>"] if add_special_tokens else [])

    def setUp(self):
        self.tokenizer = self.CharTokenizer()

    def test_short_document_contains_structure_header(self):
        result = chunk_document_single_m3(
            "doc-1",
            "速度仲裁",
            "正文内容。",
            folder_path="本体开发部 / 导航组 / 高速小车",
            tokenizer=self.tokenizer,
        )
        self.assertEqual(result["parent"], [])
        self.assertEqual(len(result["leaf"]), 1)
        content = result["leaf"][0]["content"]
        self.assertIn("知识库路径：本体开发部 / 导航组 / 高速小车", content)
        self.assertIn("文档：速度仲裁", content)
        self.assertIn("本文目录：速度仲裁", content)

    def test_outline_path_is_repeated_per_section(self):
        content = "## 第一节\n第一节正文。\n## 第二节\n第二节正文。"
        outline = json.dumps([
            {"level": 2, "title": "第一节", "line": 1, "path": "第一节"},
            {"level": 2, "title": "第二节", "line": 3, "path": "第二节"},
        ], ensure_ascii=False)
        result = chunk_document_single_m3(
            "doc-2", "文档", content, outline, tokenizer=self.tokenizer
        )
        joined = "\n".join(chunk["content"] for chunk in result["leaf"])
        self.assertIn("本文目录：第一节", joined)
        self.assertIn("本文目录：第二节", joined)

    def test_table_repeats_header(self):
        rows = [f"| {index} | {'内容' * 30} |" for index in range(30)]
        content = "| 编号 | 内容 |\n| --- | --- |\n" + "\n".join(rows)
        result = chunk_document_single_m3(
            "doc-3", "表格", content, tokenizer=self.tokenizer
        )
        self.assertGreater(len(result["leaf"]), 1)
        for chunk in result["leaf"]:
            self.assertIn("| 编号 | 内容 |", chunk["content"])
            self.assertIn("| --- | --- |", chunk["content"])
            self.assertLessEqual(chunk["token_count"], MAX_TOKENS)

    def test_code_chunks_have_balanced_fences(self):
        body = "\n".join(f"print('line-{index}')" for index in range(180))
        result = chunk_document_single_m3(
            "doc-4", "代码", f"```python\n{body}\n```", tokenizer=self.tokenizer
        )
        self.assertGreater(len(result["leaf"]), 1)
        for chunk in result["leaf"]:
            self.assertEqual(
                sum(line.lstrip().startswith("```") for line in chunk["content"].splitlines()) % 2,
                0,
            )
            self.assertLessEqual(chunk["token_count"], MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
