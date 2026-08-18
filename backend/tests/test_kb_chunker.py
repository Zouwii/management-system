import json
import unittest

from ai.knowledge.chunker import LEAF_MAX, chunk_document, count_tokens


class ChunkerMvpTests(unittest.TestCase):
    def assert_valid(self, result, doc_id):
        leaves = result["leaf"]
        self.assertTrue(leaves)
        self.assertEqual([c["doc_id"] for c in leaves], [doc_id] * len(leaves))
        self.assertEqual([c["chunk_index"] for c in leaves], list(range(len(leaves))))
        self.assertTrue(all(c["content"].strip() for c in leaves))
        self.assertTrue(all(count_tokens(c["content"]) <= LEAF_MAX for c in leaves))

    def test_short_document_has_metadata_and_hard_limit(self):
        result = chunk_document("doc-1", "短文", "中文" * 499)
        self.assert_valid(result, "doc-1")

    def test_preamble_before_first_outline_entry_is_preserved(self):
        content = "摘要说明\n这是标题前正文。\n## 第一节\n正文内容。\n## 第二节\n更多内容。"
        outline = json.dumps([{"level": 2, "title": "第一节", "line": 3,
                               "path": "第一节"},
                              {"level": 2, "title": "第二节", "line": 5,
                               "path": "第二节"}])
        result = chunk_document("doc-2", "文档", content, outline)
        self.assert_valid(result, "doc-2")
        joined = "\n".join(c["content"] for c in result["leaf"])
        self.assertIn("摘要说明", joined)
        self.assertIn("标题前正文", joined)

    def test_table_preserves_surrounding_text_and_rows(self):
        content = ("表格前说明\n\n| 名称 | 值 |\n| --- | --- |\n"
                   "| A | 1 |\n| B | 2 |\n\n表格后说明")
        result = chunk_document("doc-3", "表格文档", content, node_type="TABLE")
        self.assert_valid(result, "doc-3")
        joined = "\n".join(c["content"] for c in result["leaf"])
        for marker in ("表格前说明", "名称", "---", "A", "B", "表格后说明"):
            self.assertIn(marker, joined)

    def test_unpunctuated_oversize_text_is_bounded_without_truncation(self):
        content = "开头标记" + ("无标点会议内容" * 1200) + "结尾标记"
        result = chunk_document("doc-4", "会议纪要", content)
        self.assert_valid(result, "doc-4")
        joined = "".join(c["content"] for c in result["leaf"])
        self.assertIn("开头标记", joined)
        self.assertIn("结尾标记", joined)
        self.assertEqual(joined, content)

    def test_parent_declares_exact_child_leaf_indexes(self):
        content = "\n\n".join(
            f"第{i}段：" + ("这是用于验证父子块精确映射的正文。" * 30)
            for i in range(40)
        )
        result = chunk_document("doc-parent", "长文档", content)
        leaves = result["leaf"]
        parents = result["parent"]

        self.assertGreater(len(parents), 1)
        declared_indexes = []
        for parent in parents:
            child_indexes = parent["child_chunk_indexes"]
            self.assertTrue(child_indexes)
            self.assertEqual(child_indexes, sorted(child_indexes))
            self.assertTrue(all(0 <= index < len(leaves) for index in child_indexes))
            expected_content = "\n\n".join(
                leaves[index]["content"] for index in child_indexes
            ).strip()
            self.assertEqual(parent["content"], expected_content)
            self.assertEqual(parent["token_count"], count_tokens(expected_content))
            declared_indexes.extend(child_indexes)

        self.assertEqual(declared_indexes, list(range(len(leaves))))


if __name__ == "__main__":
    unittest.main()
