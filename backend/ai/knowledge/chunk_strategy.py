"""Select the configured chunking strategy without changing the storage API."""

from __future__ import annotations

import os

from ai.knowledge.chunker import chunk_document
from ai.knowledge.single_m3_chunker import chunk_document_single_m3


def chunk_document_for_index(
    doc_id: str,
    title: str,
    content: str,
    outline_json: str = "",
    node_type: str = "FILE",
    folder_path: str = "",
) -> dict:
    strategy = (os.getenv("KB_CHUNK_STRATEGY") or "parent_child").strip().lower()
    if strategy in {"single_m3", "single-m3", "m3"}:
        return chunk_document_single_m3(
            doc_id,
            title,
            content,
            outline_json,
            node_type,
            folder_path,
        )
    return chunk_document(doc_id, title, content, outline_json, node_type)
