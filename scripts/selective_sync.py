#!/usr/bin/env python3
"""定向拉取指定文件夹下的文件，填充 breadcrumb 路径，支持递归.

用法:
  python selective_sync.py <ws_id> <folder_node_id> [--dry-run] [--recursive] [--target errcode|kb] [--with-content]

示例:
  # 递归拉取 + 下载正文
  python selective_sync.py nb9XJV8Pky0yOXy AY39rGpMPmeVNxR7ryyl8OZkXKnaoNQ7 --recursive --with-content

  # 只拉元数据
  python selective_sync.py nb9XJV8Pky0yOXy EGd6jK4Nvk3JlBz3qbYGWZOP0LawMmQq --recursive
"""

import sys, json, re
sys.path.insert(0, "/home/jz/zhr/tb_tool_bt/backend")

from ai.knowledge.service import DingTalkKnowledgeClient
from ai.knowledge.parser import blocks_to_markdown
from base.db.engine import SessionLocal
from base.db.orm import UserCharacter as DbUserCharacter
from datetime import datetime, timezone
import pymysql
from collections import deque


def get_union_id():
    db = SessionLocal()
    try:
        row = db.query(DbUserCharacter).filter(
            DbUserCharacter.union_id.isnot(None),
            DbUserCharacter.union_id != ""
        ).first()
        return row.union_id if row else None
    finally:
        db.close()


def resolve_breadcrumb(client, node_id, workspace_id):
    """从叶子节点往上回溯，拼出完整面包屑路径."""
    parts = []
    current = node_id
    visited = set()
    while current and current not in visited and current != "root":
        visited.add(current)
        detail = client.get_node_detail(current)
        if not detail.get("ok"):
            break
        node = detail.get("data", {})
        name = node.get("name", "") or ""
        if name:
            parts.append(name)
        pid = node.get("parentId", "") or node.get("parentNodeId", "")
        if pid == current or not pid:
            break
        current = pid
    parts.reverse()
    return " / ".join(parts)


def parse_error_code(title):
    """从标题中提取错误码和错误描述.

    "615038 地图数据读取错误.adoc" → ("615038", "地图数据读取错误")
    "错误码问题的综合说明.adoc"   → (None, None)
    """
    name = title
    for ext in (".adoc", ".axls", ".txt", ".md", ".dlink", ".docx"):
        if name.endswith(ext):
            name = name[:-len(ext)]
            break

    m = re.match(r'^(\d{5,7})\s*(.*)', name)
    if m:
        code = m.group(1)
        desc = m.group(2).strip()
        return code, desc if desc else None
    return None, None


def fetch_content(client, node_id, category):
    """从钉钉 API 拉取文档正文并转为 Markdown.

    返回 (content, raw_json_str) 或 ("", "SKIPPED") 降级.
    """
    if category == "ALIDOC":
        result = client.get_document_blocks(node_id)
        if result.get("ok"):
            blocks = result.get("data", [])
            md = blocks_to_markdown(blocks)
            return md, json.dumps(result, ensure_ascii=False)
        else:
            return "", json.dumps(result, ensure_ascii=False)

    elif category == "WORKBOOK":
        # workbook 暂不解析内容
        return "", json.dumps({"note": "WORKBOOK content not fetched"}, ensure_ascii=False)

    # OTHER / unknown
    return "", "SKIPPED"


def _upsert_errcode(cursor, client, workspace_id, folder_node_id, f, breadcrumb, now, with_content):
    """插入或更新一条 errcode_documents 记录."""
    nid = f["nodeId"]
    title = f["name"]
    cat = f.get("category", "")
    bc = breadcrumb + " / " + title

    error_code, error_desc = parse_error_code(title)

    # 下载正文
    content = ""
    raw_json_str = json.dumps(f, ensure_ascii=False)
    if with_content and cat in ("ALIDOC", "WORKBOOK"):
        content, raw_json_str = fetch_content(client, nid, cat)

    cursor.execute("SELECT id FROM errcode_documents WHERE doc_id=%s", (nid,))
    exists = cursor.fetchone()
    if exists:
        cursor.execute(
            "UPDATE errcode_documents SET breadcrumb=%s, updated_at=%s, parent_id=%s, "
            "error_code=COALESCE(error_code,%s), error_desc=COALESCE(error_desc,%s)"
            + (", content=%s, raw_json=%s" if with_content else "")
            + " WHERE doc_id=%s",
            (bc, now, folder_node_id, error_code, error_desc,
             content, raw_json_str, nid) if with_content
            else (bc, now, folder_node_id, error_code, error_desc, nid)
        )
        return "UPD", bc
    else:
        cursor.execute(
            "INSERT INTO errcode_documents "
            "(doc_id, error_code, workspace_id, title, node_type, parent_id, "
            " content, raw_json, category, breadcrumb, error_desc, synced_at, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (nid, error_code, workspace_id, title, "FILE", folder_node_id,
             content, raw_json_str,
             cat, bc, error_desc, now, now, now)
        )
        return "NEW", bc


def _upsert_kb(cursor, client, workspace_id, folder_node_id, f, breadcrumb, now, with_content):
    """插入或更新一条 kb_documents 记录."""
    nid = f["nodeId"]
    title = f["name"]
    cat = f.get("category", "")
    bc = breadcrumb + " / " + title

    content = ""
    raw_json_str = json.dumps(f, ensure_ascii=False)
    if with_content and cat in ("ALIDOC", "WORKBOOK"):
        content, raw_json_str = fetch_content(client, nid, cat)

    cursor.execute("SELECT id FROM kb_documents WHERE doc_id=%s", (nid,))
    exists = cursor.fetchone()
    if exists:
        cols = "breadcrumb=%s, updated_at=%s, parent_id=%s"
        params = [bc, now, folder_node_id]
        if with_content:
            cols += ", content=%s, raw_json=%s"
            params.extend([content, raw_json_str])
        params.append(nid)
        cursor.execute(f"UPDATE kb_documents SET {cols} WHERE doc_id=%s", params)
        return "UPD", bc
    else:
        cursor.execute(
            "INSERT INTO kb_documents "
            "(doc_id, workspace_id, title, node_type, parent_id, content, raw_json, "
            " synced_at, created_at, updated_at, category, breadcrumb) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (nid, workspace_id, title, "FILE", folder_node_id,
             content, raw_json_str,
             now, now, now, cat, bc)
        )
        return "NEW", bc


def sync_recursive(workspace_id, folder_node_id, target="errcode", with_content=False, dry_run=False):
    """递归同步：拉取目录下所有层级的文件.

    使用广度优先遍历，避免 API 调用爆炸和递归过深.
    target: "errcode" → errcode_documents, "kb" → kb_documents
    with_content: 是否拉取正文（慢）
    """
    union_id = get_union_id()
    if not union_id:
        print("ERROR: no union_id found")
        return

    upsert_fn = _upsert_errcode if target == "errcode" else _upsert_kb
    table_name = "errcode_documents" if target == "errcode" else "kb_documents"

    client = DingTalkKnowledgeClient(union_id)
    root_breadcrumb = resolve_breadcrumb(client, folder_node_id, workspace_id)
    print(f"TARGET: {table_name}  content={'ON' if with_content else 'OFF'}")
    print(f"ROOT:   {root_breadcrumb}")
    print(f"ws={workspace_id}  node={folder_node_id}")
    print()

    now = datetime.now(timezone.utc)
    conn = None if dry_run else pymysql.connect(
        host="127.0.0.1", user="root", password="123456",
        database="kb_storage", charset="utf8mb4"
    )
    cursor = None if dry_run else conn.cursor()

    total_files = 0
    total_folders = 0
    queue = deque()
    queue.append((folder_node_id, root_breadcrumb, 0))

    while queue:
        parent_id, parent_breadcrumb, depth = queue.popleft()
        indent = "  " * depth

        result = client.list_nodes(workspace_id, parent_id)
        if not result.get("ok"):
            print(f"{indent}⚠️  [{parent_id[:8]}...] ERROR: {result.get('error')}")
            continue

        nodes = result.get("data", [])
        files = [n for n in nodes if n["type"] == "FILE"]
        folders = [n for n in nodes if n["type"] == "FOLDER"]

        if depth == 0:
            print(f"{indent}📁 {parent_breadcrumb}  ({len(files)} files, {len(folders)} sub-folders)")
            print()

        for f in files:
            if dry_run:
                ec, ed = parse_error_code(f.get("name", ""))
                tag = f"  [{ec}]" if ec else ""
                print(f"{indent}  📄 {f.get('name', '')}{tag}")
            else:
                act, path = upsert_fn(cursor, client, workspace_id, parent_id, f, parent_breadcrumb, now, with_content)
                ec, ed = parse_error_code(f.get("name", ""))
                tag = f"  [{ec}]" if ec else ""
                size_hint = f"  [{len(path.split('/')[-1].encode('utf-8'))}B]" if with_content else ""
                print(f"{indent}  [{act}] {f.get('name', '')}{tag}")
            total_files += 1

        for f in folders:
            fn = f.get("name", "")
            fid = f.get("nodeId", "")
            child_breadcrumb = parent_breadcrumb + " / " + fn
            if dry_run:
                print(f"{indent}  📁 {fn}/  ({fid[:8]}...)  hasChildren={f.get('hasChildren', False)}")
            else:
                print(f"{indent}  📁 {fn}/  ({fid[:8]}...)")
            total_folders += 1
            queue.append((fid, child_breadcrumb, depth + 1))

    if not dry_run and cursor:
        conn.commit()
        cursor.close()
        conn.close()

    print()
    print(f"Done: {total_files} files + {total_folders} folders → {table_name}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python selective_sync.py <ws_id> <folder_node_id> [--dry-run] [--recursive] [--target errcode|kb] [--with-content]")
        print()
        print("Examples:")
        print("  # Recursive sync with content download")
        print("  python selective_sync.py nb9XJV8Pky0yOXy AY39rGpMPmeVNxR7ryyl8OZkXKnaoNQ7 --recursive --with-content")
        print()
        print("  # Dry-run preview")
        print("  python selective_sync.py nb9XJV8Pky0yOXy EGd6jK4Nvk3JlBz3qbYGWZOP0LawMmQq --recursive --dry-run")
        sys.exit(1)

    ws_id = sys.argv[1]
    node_id = sys.argv[2]
    dry = "--dry-run" in sys.argv
    recursive = "--recursive" in sys.argv
    with_content = "--with-content" in sys.argv
    target = "errcode"
    for i, a in enumerate(sys.argv):
        if a == "--target" and i + 1 < len(sys.argv):
            target = sys.argv[i + 1]
            break

    if recursive:
        sync_recursive(ws_id, node_id, target=target, with_content=with_content, dry_run=dry)
    else:
        # Legacy single-level mode
        client = DingTalkKnowledgeClient(get_union_id())
        result = client.list_nodes(ws_id, node_id)
        if not result.get("ok"):
            print("ERROR:", result.get("error"))
            sys.exit(1)
        nodes = result.get("data", [])
        files = [n for n in nodes if n["type"] == "FILE"]
        folders = [n for n in nodes if n["type"] == "FOLDER"]
        breadcrumb = resolve_breadcrumb(client, node_id, ws_id)
        print(f"Folder: {breadcrumb}")
        print(f"Children: {len(files)} files + {len(folders)} folders")
        print()
        if folders:
            print("--- Sub-folders (not pulled) ---")
            for f in folders:
                print(f"  [FOLDER] {f.get('name', '')}  =>  {f.get('nodeId', '')}")
        print()
        for i, f in enumerate(files, 1):
            ec, ed = parse_error_code(f.get("name", ""))
            tag = f"  [{ec}]" if ec else ""
            print(f"  {i}. {f.get('name', '')}{tag}")
        print(f"\n[DRY RUN]") if dry else print("Use --recursive for full sync")


