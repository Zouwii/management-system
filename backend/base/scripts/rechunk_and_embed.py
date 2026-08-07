#!/usr/bin/env python3
"""手动执行 Phase 2 (rechunk) + Phase 3 (embed)，带完整日志。

用法（在服务器 backend/ 目录下执行）:
  python3 scripts/rechunk_and_embed.py           # 全量 rechunk + embed
  python3 scripts/rechunk_and_embed.py --check   # 只查看当前状态，不执行
  python3 scripts/rechunk_and_embed.py --rechunk-only  # 只 rechunk
  python3 scripts/rechunk_and_embed.py --embed-only    # 只 embed
  python3 scripts/rechunk_and_embed.py --doc-id abc123  # 只处理指定文档
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# 确保能找到 backend 模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timezone

_LOG_FILE = (
    Path(__file__).resolve().parent.parent
    / "runtime" / "logs" / "ai_sync_embed.log"
)
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── 日志 ──────────────────────────────────────────────────────────

def log(entry: dict) -> None:
    entry.setdefault("ts", int(time.time()))
    msg = json.dumps(entry, ensure_ascii=False)
    print(f"  [{entry.get('phase','?')}] {entry.get('event','?')}: {entry.get('msg','')}")
    try:
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

# ── 状态检查 ──────────────────────────────────────────────────────

def check_state() -> dict:
    """查询当前数据库状态并打印。"""
    from base.db.engine import KbSessionLocal, PgVectorSessionLocal
    from sqlalchemy import text

    db = KbSessionLocal()
    try:
        doc_total = db.execute(text("SELECT COUNT(*) FROM kb_documents")).scalar()
        doc_with_content = db.execute(
            text("SELECT COUNT(*) FROM kb_documents WHERE content != ''")
        ).scalar()
        chunk_total = db.execute(text("SELECT COUNT(*) FROM kb_chunks")).scalar()
        chunk_docs = db.execute(
            text("SELECT COUNT(DISTINCT doc_id) FROM kb_chunks")
        ).scalar()

        # 最近同步时间
        last_sync = db.execute(
            text("SELECT MAX(synced_at) FROM kb_documents")
        ).scalar()
    finally:
        db.close()

    # pgvector
    pg = PgVectorSessionLocal()
    try:
        pg_total = pg.execute(text("SELECT COUNT(*) FROM chunk_vectors")).scalar()
    except Exception as e:
        pg_total = f"ERROR: {e}"
    finally:
        pg.close()

    state = {
        "documents_total": doc_total,
        "documents_with_content": doc_with_content,
        "chunks_total": chunk_total,
        "chunks_covering_docs": chunk_docs,
        "vectors_total": pg_total,
        "last_sync": str(last_sync) if last_sync else None,
    }

    print("=" * 60)
    print("  当前数据库状态")
    print("=" * 60)
    print(f"  kb_documents (总文档):      {doc_total:>8}")
    print(f"  kb_documents (有内容):      {doc_with_content:>8}")
    print(f"  kb_chunks (分块总数):       {chunk_total:>8}")
    print(f"  kb_chunks (覆盖文档数):     {chunk_docs:>8}")
    print(f"  chunk_vectors (向量总数):   {pg_total}")
    print(f"  最近同步时间:               {last_sync}")
    print()
    return state


# ── Phase 2: Rechunk ──────────────────────────────────────────────

def run_rechunk(doc_id: str = "") -> dict:
    """对所有有内容的文档（或指定文档）执行分块。"""
    from ai.knowledge.chunker import chunk_document
    from ai.knowledge.models import KbDocument, KbChunk
    from ai.knowledge.models import create_kb_fts, drop_kb_fts
    from base.db.engine import KbSessionLocal, kb_engine

    db = KbSessionLocal()
    try:
        if doc_id:
            docs = db.query(KbDocument).filter(
                KbDocument.doc_id == doc_id,
                KbDocument.content != "",
            ).all()
        else:
            docs = db.query(KbDocument).filter(
                KbDocument.content != "",
            ).all()

        if not docs:
            log({"phase": "rechunk", "event": "skip",
                 "msg": f"没有可处理文档 (doc_id={doc_id or 'all'})"})
            return {"chunkedDocs": 0, "totalChunks": 0, "skipped": True}

        log({"phase": "rechunk", "event": "start",
             "msg": f"开始分块 {len(docs)} 个文档"})

        total_chunks = 0
        t0 = time.time()
        for i, doc in enumerate(docs):
            # 删除旧分块
            deleted = db.query(KbChunk).filter(
                KbChunk.doc_id == doc.doc_id
            ).delete()
            # 生成新分块
            result = chunk_document(doc.doc_id, doc.title,
                                    doc.content, doc.outline or "", doc.node_type)
            for c_list in (result.get("leaf", []), result.get("parent", [])):
                for c in c_list:
                    db.add(KbChunk(
                        doc_id=c["doc_id"],
                        chunk_index=c["chunk_index"],
                        content=c["content"],
                        token_count=c["token_count"],
                        parent_id=c.get("parent_id"),
                        depth=c.get("depth", 1),
                        chunk_type=c.get("chunk_type", "paragraph"),
                        section_path=c.get("section_path", ""),
                    ))
            total_chunks += len(result.get("leaf", [])) + len(result.get("parent", []))

            if (i + 1) % 50 == 0:
                db.commit()
                print(f"    进度: {i+1}/{len(docs)} 文档, {total_chunks} 个分块")

        db.commit()
        elapsed = round(time.time() - t0, 1)

        # 重建 FTS 索引
        print("  重建全文索引...")
        try:
            drop_kb_fts(kb_engine)
            create_kb_fts(kb_engine)
        except Exception as e:
            print(f"  FTS 索引重建失败（MySQL 会自动维护）: {e}")

        log({"phase": "rechunk", "event": "done",
             "msg": f"完成: {len(docs)} 文档 → {total_chunks} 分块, 耗时 {elapsed}s",
             "doc_count": len(docs), "total_chunks": total_chunks,
             "elapsed_sec": elapsed})

        return {"chunkedDocs": len(docs), "totalChunks": total_chunks,
                "elapsedSec": elapsed}

    except Exception as e:
        db.rollback()
        log({"phase": "rechunk", "event": "error",
             "msg": str(e), "error": str(e)})
        raise
    finally:
        db.close()


# ── Phase 3: Embed ────────────────────────────────────────────────

def run_embed() -> dict:
    """对所有未嵌入向量的分块执行 embedding。"""
    from ai.knowledge.embedder import embed_chunks

    log({"phase": "embed", "event": "start",
         "msg": "开始 embedding（跳过已有向量的 chunk）"})

    t0 = time.time()
    stats = embed_chunks(limit=0)  # limit=0 表示不限制
    elapsed = round(time.time() - t0, 1)

    log({"phase": "embed", "event": "done",
         "msg": (f"完成: total={stats.get('chunk_total',0)} "
                 f"new={stats.get('embedded',0)} "
                 f"skipped={stats.get('skipped',0)} "
                 f"errors={stats.get('errors',0)}, "
                 f"耗时 {elapsed}s"),
         "chunk_total": stats.get("chunk_total", 0),
         "embedded": stats.get("embedded", 0),
         "skipped": stats.get("skipped", 0),
         "errors": stats.get("errors", 0),
         "elapsed_sec": elapsed})

    return stats


# ── 主入口 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="手动 rechunk + embed")
    parser.add_argument("--check", action="store_true",
                        help="只查看状态，不执行操作")
    parser.add_argument("--rechunk-only", action="store_true",
                        help="只执行 rechunk")
    parser.add_argument("--embed-only", action="store_true",
                        help="只执行 embed")
    parser.add_argument("--doc-id", type=str, default="",
                        help="只处理指定文档 ID")
    args = parser.parse_args()

    log({"phase": "script", "event": "start",
         "msg": f"rechunk_and_embed.py (check={args.check}, "
                f"rechunk_only={args.rechunk_only}, "
                f"embed_only={args.embed_only}, doc_id={args.doc_id or 'all'})"})

    # ── 执行前状态 ──
    print()
    print("[步骤 0] 执行前状态")
    state_before = check_state()

    if args.check:
        print("--check 模式，不执行操作。")
        log({"phase": "script", "event": "done",
             "msg": "check-only mode", "state_before": state_before})
        return

    # ── Phase 2: Rechunk ──
    if not args.embed_only:
        print("[步骤 1] Phase 2: Rechunk")
        try:
            rechunk_result = run_rechunk(doc_id=args.doc_id)
            print(f"  结果: {rechunk_result.get('chunkedDocs',0)} 文档 → "
                  f"{rechunk_result.get('totalChunks',0)} 分块, "
                  f"耗时 {rechunk_result.get('elapsedSec',0)}s")
        except Exception as e:
            print(f"  ❌ Rechunk 失败: {e}")
            log({"phase": "script", "event": "error",
                 "msg": f"rechunk failed: {e}"})
            return
        print()

    # ── Phase 3: Embed ──
    if not args.rechunk_only:
        print("[步骤 2] Phase 3: Embed")
        try:
            embed_result = run_embed()
            print(f"  结果: total={embed_result.get('chunk_total',0)}, "
                  f"new={embed_result.get('embedded',0)}, "
                  f"skipped={embed_result.get('skipped',0)}, "
                  f"errors={embed_result.get('errors',0)}, "
                  f"耗时 {embed_result.get('elapsed_sec',0)}s")
        except Exception as e:
            print(f"  ❌ Embed 失败: {e}")
            log({"phase": "script", "event": "error",
                 "msg": f"embed failed: {e}"})
            return
        print()

    # ── 执行后状态 ──
    print("[步骤 3] 执行后状态")
    state_after = check_state()

    # ── 对比 ──
    print("=" * 60)
    print("  执行前后对比")
    print("=" * 60)
    changes = {
        "分块增量": f"{state_after['chunks_total']} - {state_before['chunks_total']} "
                    f"= {state_after['chunks_total'] - state_before['chunks_total']}",
        "向量增量": f"{state_after['vectors_total']} - {state_before['vectors_total']} "
                    f"= {state_after['vectors_total'] - state_before['vectors_total']}"
                    if isinstance(state_after['vectors_total'], int)
                    and isinstance(state_before['vectors_total'], int)
                    else "N/A",
    }
    for k, v in changes.items():
        print(f"  {k}: {v}")

    log({"phase": "script", "event": "done",
         "msg": "完成", "state_before": state_before,
         "state_after": state_after, "changes": changes})

    print()
    print("日志已写入:", _LOG_FILE)


if __name__ == "__main__":
    main()
