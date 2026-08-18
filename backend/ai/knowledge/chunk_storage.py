"""Persistence helpers for leaf chunks and their supporting parents."""

from __future__ import annotations

from typing import Any, Dict, List

from ai.knowledge.models import KbChunk


def _validate_parent_contract(
    leaves: List[dict], parents: List[dict],
) -> Dict[int, dict]:
    leaves_by_index: Dict[int, dict] = {}
    for leaf in leaves:
        index = leaf.get("chunk_index")
        if not isinstance(index, int) or index < 0:
            raise ValueError(f"invalid leaf chunk_index: {index!r}")
        if index in leaves_by_index:
            raise ValueError(f"duplicate leaf chunk_index: {index}")
        leaves_by_index[index] = leaf

    parent_indexes: set[int] = set()
    assigned_children: set[int] = set()
    for parent in parents:
        parent_index = parent.get("chunk_index")
        if not isinstance(parent_index, int) or parent_index in parent_indexes:
            raise ValueError(f"invalid or duplicate parent chunk_index: {parent_index!r}")
        parent_indexes.add(parent_index)
        child_indexes = parent.get("child_chunk_indexes")
        if not isinstance(child_indexes, list) or not child_indexes:
            raise ValueError(
                f"parent {parent.get('chunk_index')!r} has no child_chunk_indexes"
            )
        if len(child_indexes) != len(set(child_indexes)):
            raise ValueError(
                f"parent {parent.get('chunk_index')!r} contains duplicate children"
            )
        missing = [index for index in child_indexes if index not in leaves_by_index]
        if missing:
            raise ValueError(
                f"parent {parent.get('chunk_index')!r} references missing leaves: {missing}"
            )
        duplicate_owners = [
            index for index in child_indexes if index in assigned_children
        ]
        if duplicate_owners:
            raise ValueError(
                f"leaf chunks assigned to multiple parents: {duplicate_owners}"
            )
        child_doc_ids = {leaves_by_index[index].get("doc_id") for index in child_indexes}
        if child_doc_ids != {parent.get("doc_id")}:
            raise ValueError(
                f"parent {parent_index!r} and child leaves belong to different documents"
            )
        assigned_children.update(child_indexes)

    return leaves_by_index


def persist_chunk_result(db: Any, result: dict) -> dict:
    """Insert one chunk_document result and establish exact parent links.

    The caller owns the transaction. Leaves are always persisted with depth=1;
    parents with depth=0. Parents are supporting context and must not be embedded.
    """
    leaves = list(result.get("leaf") or [])
    parents = list(result.get("parent") or [])
    leaves_by_index = _validate_parent_contract(leaves, parents)

    leaf_rows_by_index: Dict[int, KbChunk] = {}
    leaf_ids: List[int] = []
    for leaf in leaves:
        row = KbChunk(
            doc_id=leaf["doc_id"],
            chunk_index=leaf["chunk_index"],
            content=leaf["content"],
            token_count=leaf["token_count"],
            parent_id=None,
            depth=1,
            chunk_type=leaf.get("chunk_type", "paragraph"),
            section_path=leaf.get("section_path", ""),
        )
        db.add(row)
        db.flush()
        leaf_rows_by_index[leaf["chunk_index"]] = row
        leaf_ids.append(row.id)

    parent_ids: List[int] = []
    for parent in parents:
        row = KbChunk(
            doc_id=parent["doc_id"],
            chunk_index=parent["chunk_index"],
            content=parent["content"],
            token_count=parent["token_count"],
            parent_id=None,
            depth=0,
            chunk_type="parent",
            section_path=parent.get("section_path", ""),
        )
        db.add(row)
        db.flush()
        parent_ids.append(row.id)
        for child_index in parent["child_chunk_indexes"]:
            leaf_rows_by_index[child_index].parent_id = row.id

    return {
        "leaf_count": len(leaves_by_index),
        "parent_count": len(parents),
        "total_count": len(leaves_by_index) + len(parents),
        "leaf_ids": leaf_ids,
        "parent_ids": parent_ids,
    }
