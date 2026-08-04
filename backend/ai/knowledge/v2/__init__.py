"""RAG v2 — File-system-based knowledge base pipeline.

Target directory: /home/jz/zhr/markdown/

Modules:
  cleaner  — Markdown cleaning layer (钉钉导出 → 干净 MD)
  scanner  — File system scanner (本地文件 → 入库)
  parser   — Markdown AST parser
  chunker  — Smart chunker
  embedder — pgvector embedder
  pipeline — Orchestration
"""
