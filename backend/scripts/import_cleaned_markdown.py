#!/usr/bin/env python3
"""RAG v3.0: 从服务器 markdown 目录批量清洗 → 写入 kb_documents content + outline.

用法（在服务器上执行）:
  cd /home/jz/zhr/tb_tool_bt/backend
  python scripts/import_cleaned_markdown.py \
      --markdown-dir /home/jz/zhr/markdown \
      --workers 5 \
      --limit 0

选项:
  --markdown-dir      markdown 文件根目录
  --workers           并发线程数 (默认 5)
  --limit             最多处理 N 篇 (0=全部)
  --skip-existing     跳过已有 content 的文档
  --dry-run           只匹配不写入

匹配策略（按优先级）:
  1. 标题行匹配: markdown 第一个 # heading ↔ kb_documents.title
  2. 文件名匹配:  文件名(去.md) ↔ kb_documents.title(去扩展名)
  3. 路径匹配:    目录层级  ↔ kb_nodes.breadcrumb → node_id
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Ensure backend is on sys.path
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from ai.knowledge.v2.cleaner import clean_markdown
from ai.knowledge.models import KbDocument, KbNode
from base.db.engine import KbSessionLocal


# ── outline extraction ───────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)(?:\s*#+\s*)?$", re.MULTILINE)
_IMPLICIT_RE = re.compile(r"^([一二三四五六七八九十]+)[、，,.)）]\s*(.+)$")


def extract_outline(markdown: str) -> List[dict]:
    """Extract heading tree from cleaned markdown.

    Returns a flat list sorted by line number, each entry:
      {level, title, line, path, source}
    """
    entries: List[dict] = []
    stack: List[dict] = []

    for lineno, line in enumerate(markdown.split("\n"), 1):
        stripped = line.strip()
        if not stripped:
            continue

        m = _HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            path_parts = [h["title"] for h in stack] + [title]
            entry = {
                "level": level,
                "title": title,
                "line": lineno,
                "path": " > ".join(path_parts),
                "source": "markdown",
            }
            entries.append(entry)
            stack.append(entry)
            continue

        m2 = _IMPLICIT_RE.match(stripped)
        if m2:
            title = stripped
            entry = {
                "level": 1,
                "title": title,
                "line": lineno,
                "path": title,
                "source": "implicit",
            }
            entries.append(entry)

    if not entries:
        first_line = markdown.strip().split("\n")[0].strip()
        if first_line:
            entries.append({
                "level": 1,
                "title": first_line[:120],
                "line": 1,
                "path": first_line[:120],
                "source": "implicit",
            })

    return entries


# ── matching ──────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    s = s.strip()
    s = re.sub(r"\.\w{2,5}$", "", s)       # remove .adoc .axls .md
    s = re.sub(r"^\d+[\.\、\s]+", "", s)    # remove leading "0. " "001."
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def _extract_title_from_md(md_text: str) -> Optional[str]:
    m = _HEADING_RE.search(md_text)
    return m.group(2).strip() if m else None


def _match_document(raw_md: str, file_path: Path, markdown_root: Path) -> Optional[dict]:
    """Try to match a markdown file to a kb_document."""
    db = KbSessionLocal()
    try:
        all_docs = db.query(KbDocument).filter(
            KbDocument.title.isnot(None),
            KbDocument.title != "",
        ).all()

        # Strategy 1: heading title match
        heading = _extract_title_from_md(raw_md)
        if heading:
            norm_h = _normalize(heading)
            for row in all_docs:
                if _normalize(row.title) == norm_h:
                    return {
                        "strategy": "heading",
                        "node_id": row.node_id,
                        "title": row.title,
                        "workspace_id": row.workspace_id,
                    }

        # Strategy 2: filename match
        norm_stem = _normalize(file_path.stem)
        if norm_stem:
            for row in all_docs:
                if _normalize(row.title) == norm_stem:
                    return {
                        "strategy": "filename",
                        "node_id": row.node_id,
                        "title": row.title,
                        "workspace_id": row.workspace_id,
                    }

        # Strategy 3: breadcrumb path match via kb_nodes
        try:
            rel_dir = file_path.parent.relative_to(markdown_root)
            parts = [p for p in rel_dir.parts if p]
            for depth in range(min(4, len(parts)), 0, -1):
                suffix = " / ".join(parts[-depth:]) + " / " + file_path.stem
                nodes = db.query(KbNode).filter(
                    KbNode.breadcrumb.like(f"%{suffix}%")
                ).all()
                if nodes:
                    doc = db.query(KbDocument).filter(
                        KbDocument.node_id == nodes[0].node_id
                    ).first()
                    if doc:
                        return {
                            "strategy": f"breadcrumb_d{depth}",
                            "node_id": doc.node_id,
                            "title": doc.title,
                            "workspace_id": doc.workspace_id,
                        }
        except ValueError:
            pass

        return None
    finally:
        db.close()


# ── worker ────────────────────────────────────────────────────────

def process_one(file_path: Path, markdown_root: Path,
                skip_existing: bool, dry_run: bool) -> dict:
    """Process a single markdown file."""
    result = {
        "file": str(file_path),
        "status": "unknown",
        "node_id": "",
        "title": "",
        "strategy": "",
        "cleaner_warnings": [],
        "outline_count": 0,
        "error": "",
    }

    try:
        raw_md = file_path.read_text(encoding="utf-8")
    except Exception as e:
        result["status"] = "read_error"
        result["error"] = str(e)
        return result

    match = _match_document(raw_md, file_path, markdown_root)
    if not match:
        result["status"] = "no_match"
        return result

    result["node_id"] = match["node_id"]
    result["title"] = match["title"]
    result["strategy"] = match["strategy"]

    clean_result = clean_markdown(raw_md, match.get("title", ""))
    cleaned = clean_result.cleaned_md
    result["cleaner_warnings"] = clean_result.warnings

    outline_entries = extract_outline(cleaned)
    result["outline_count"] = len(outline_entries)

    if dry_run:
        result["status"] = "dry_run"
        return result

    db = KbSessionLocal()
    try:
        row = db.query(KbDocument).filter(
            KbDocument.node_id == match["node_id"]
        ).first()
        if not row:
            result["status"] = "db_row_missing"
            return result

        if skip_existing and (row.content or "").strip():
            result["status"] = "skipped_existing"
            return result

        now = datetime.now(timezone.utc)
        row.content = cleaned
        row.outline = json.dumps(outline_entries, ensure_ascii=False)
        row.fetch_status = "success"
        row.fail_reason = ""
        row.synced_at = now
        row.updated_at = now

        db.commit()
        result["status"] = "ok"
    except Exception as e:
        db.rollback()
        result["status"] = "db_error"
        result["error"] = str(e)
    finally:
        db.close()

    return result


# ── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAG v3.0: 批量清洗 markdown → kb_documents")
    parser.add_argument("--markdown-dir", "-d", required=True, help="markdown 根目录")
    parser.add_argument("--workers", "-w", type=int, default=5)
    parser.add_argument("--limit", "-l", type=int, default=0, help="最多 N 篇 (0=全部)")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有 content")
    parser.add_argument("--dry-run", action="store_true", help="只匹配不写入")
    args = parser.parse_args()

    md_root = Path(args.markdown_dir)
    if not md_root.is_dir():
        print(f"❌ 目录不存在: {md_root}", flush=True)
        sys.exit(1)

    md_files = sorted(
        f for f in md_root.rglob("*.md")
        if not f.name.startswith("_")
    )
    if args.limit > 0:
        md_files = md_files[: args.limit]

    print(f"📂 扫描到 {len(md_files)} 个 .md 文件", flush=True)
    print(f"🧵 并发: {args.workers}", flush=True)
    if args.dry_run:
        print(f"🔍 DRY-RUN 模式: 只匹配不写入", flush=True)
    print(f"{'='*60}", flush=True)

    stats: Dict[str, int] = {}
    total = len(md_files)
    completed = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_one, f, md_root, args.skip_existing, args.dry_run): f
            for f in md_files
        }
        for future in as_completed(futures):
            r = future.result()
            completed += 1
            s = r["status"]
            stats[s] = stats.get(s, 0) + 1

            if s == "ok":
                print(f"  ✅ [{completed}/{total}] {r['title'][:50]:<50} "
                      f"outline={r['outline_count']} by={r['strategy']}", flush=True)
            elif s == "dry_run":
                print(f"  🔍 [{completed}/{total}] {r['title'][:50]:<50} "
                      f"→ matched by={r['strategy']}", flush=True)
            elif s == "no_match":
                print(f"  ⚠️ [{completed}/{total}] {Path(r['file']).name[:55]:<55} "
                      f"→ 无法匹配", flush=True)
            elif s == "skipped_existing":
                print(f"  ⏭ [{completed}/{total}] {r['title'][:50]:<50} (已有内容)", flush=True)
            else:
                print(f"  ❌ [{completed}/{total}] {Path(r['file']).name[:55]:<55} "
                      f"{s}: {r.get('error', '')[:80]}", flush=True)

    elapsed = time.time() - start
    print(f"\n{'='*60}", flush=True)
    print(f"📊 ok={stats.get('ok', 0)}  dry_run={stats.get('dry_run', 0)}  "
          f"no_match={stats.get('no_match', 0)}  "
          f"skipped={stats.get('skipped_existing', 0)}  "
          f"err={stats.get('read_error', 0) + stats.get('db_error', 0) + stats.get('db_row_missing', 0)}",
          flush=True)
    if elapsed > 0:
        print(f"⏱ {elapsed:.1f}s ({total/elapsed:.1f} 篇/s)", flush=True)

    # Save summary
    summary = {
        "total": total,
        "stats": stats,
        "elapsed_s": round(elapsed, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = md_root / "_import_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📋 {summary_path}", flush=True)


if __name__ == "__main__":
    main()
