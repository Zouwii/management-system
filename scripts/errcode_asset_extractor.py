#!/usr/bin/env python3
"""errcode 子项目 — 图片/附件提取器（不修改主 RAG 流程）

用法:
  python errcode_asset_extractor.py <doc_id>          # 单篇
  python errcode_asset_extractor.py --all              # 全量 errcode_documents
"""

import sys, json, re
sys.path.insert(0, "/home/jz/zhr/tb_tool_bt/backend")

from ai.knowledge.service import DingTalkKnowledgeClient
from base.db.engine import SessionLocal
from base.db.orm import UserCharacter as DbUserCharacter
from datetime import datetime, timezone
import pymysql


def get_client():
    db = SessionLocal()
    try:
        row = db.query(DbUserCharacter).filter(
            DbUserCharacter.union_id.isnot(None),
            DbUserCharacter.union_id != ""
        ).first()
        return DingTalkKnowledgeClient(row.union_id) if row else None
    finally:
        db.close()


def extract_assets(client, doc_id, error_code=""):
    """从文档 blocks 中提取图片、附件、表格."""
    assets = []
    result = client.get_document_blocks(doc_id)
    if not result.get("ok"):
        return assets

    blocks = result.get("data", [])
    full_text = []

    for b in blocks:
        bt = b.get("blockType", "")
        body = b.get(bt, {})

        # 1. attachment blocks
        if bt == "attachment":
            assets.append({
                "type": "attachment",
                "name": body.get("name", ""),
                "viewType": body.get("viewType", ""),
                "ref": f"[附件: {body.get('name', '')}]",
            })

        # 2. picture blocks (if DingTalk ever adds them)
        elif bt == "picture":
            assets.append({
                "type": "image",
                "name": body.get("name", ""),
                "url": body.get("url", body.get("src", "")),
                "ref": f"[图片: {body.get('name', '')}]",
            })

        # 3. table blocks
        elif bt == "table":
            rows = len(body.get("cells", []))
            if rows > 0:
                assets.append({
                    "type": "table",
                    "name": f"表格({rows}行)",
                    "ref": f"[表格: {rows}行]",
                })

        # 4. inline images in paragraph text ![](url)
        elif bt in ("paragraph", "heading"):
            text = body.get("text", "") or ""
            full_text.append(text)
            # Match ![](url) or ![alt](url)
            for m in re.finditer(r'!\[([^\]]*)\]\(([^)]+)\)', text):
                assets.append({
                    "type": "image",
                    "name": m.group(1) or "inline_image",
                    "url": m.group(2),
                    "ref": f"![{m.group(1)}]({m.group(2)})",
                })

    return assets


def save_assets(cursor, doc_id, error_code, assets, now):
    """写入 errcode_assets 表."""
    saved = 0
    for a in assets:
        cursor.execute(
            "INSERT INTO errcode_assets (doc_id, error_code, asset_type, asset_name, asset_url, asset_ref, created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (doc_id, error_code, a["type"], a.get("name", ""),
             a.get("url", ""), a.get("ref", ""), now)
        )
        saved += 1
    return saved


if __name__ == "__main__":
    client = get_client()
    if not client:
        print("ERROR: no user")
        sys.exit(1)

    conn = pymysql.connect(host="127.0.0.1", user="root", password="123456",
                           database="kb_storage", charset="utf8mb4")
    cursor = conn.cursor()
    now = datetime.now(timezone.utc)

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        cursor.execute("SELECT doc_id, error_code FROM errcode_documents")
        rows = cursor.fetchall()
        total = 0
        for doc_id, code in rows:
            assets = extract_assets(client, doc_id, code)
            n = save_assets(cursor, doc_id, code, assets, now)
            total += n
            if assets:
                print(f"[{code}] {len(assets)} assets")
        conn.commit()
        print(f"\nTotal: {total} assets from {len(rows)} docs")
    elif len(sys.argv) > 1:
        doc_id = sys.argv[1]
        cursor.execute("SELECT error_code FROM errcode_documents WHERE doc_id=%s", (doc_id,))
        row = cursor.fetchone()
        code = row[0] if row else ""
        assets = extract_assets(client, doc_id, code)
        n = save_assets(cursor, doc_id, code, assets, now)
        conn.commit()
        print(f"Extracted {n} assets:")
        for a in assets:
            print(f"  [{a['type']}] {a['name']}")
    else:
        print("Usage: python errcode_asset_extractor.py <doc_id> | --all")

    cursor.close()
    conn.close()
