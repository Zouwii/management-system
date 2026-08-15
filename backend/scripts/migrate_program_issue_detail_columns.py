#!/usr/bin/env python3
"""program_issue_detail 表列重命名 & 新增 & 数据回填。

按设计文档 program-issue-design.md 执行：
  1. 重命名 5 列：project_category_1→project_catagory_1, vehicle_type_2→project_catagory_2,
                    project_name_3→project_catagory_3, problem_type_level_1→problem_type_1,
                    problem_type_level_2→problem_type_2
  2. 删除 1 列：problem_type_level_3
  3. 新增 5 列：vehicle_1, vehicle_2, problem_note_info_1/2/3
  4. 从 custom_fields_json 解析并回填车型 + 问题提示信息

用法：
  python scripts/migrate_program_issue_detail_columns.py --dry-run
  python scripts/migrate_program_issue_detail_columns.py
  python scripts/migrate_program_issue_detail_columns.py --limit 100
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import inspect, text

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from base.db.engine import SessionLocal, engine

# ── customField ID 常量 ──
VEHICLE_FIELD_ID = "668e05afbe23298626d61027"
PROBLEM_NOTE_INFO_FIELD_ID = "67c572129590cd29ac9c5137"

# ── 重命名映射（旧名 → 新名）──
RENAME_MAP = {
    "project_category_1": "project_catagory_1",
    "vehicle_type_2": "project_catagory_2",
    "project_name_3": "project_catagory_3",
    "problem_type_level_1": "problem_type_1",
    "problem_type_level_2": "problem_type_2",
}

# ── 新增列 ──
NEW_COLUMNS = {
    "vehicle_1": "VARCHAR(128)",
    "vehicle_2": "VARCHAR(128)",
    "problem_note_info_1": "VARCHAR(128)",
    "problem_note_info_2": "VARCHAR(128)",
    "problem_note_info_3": "VARCHAR(256)",
}

# ── 删除列 ──
DROP_COLUMNS = ("problem_type_level_3",)


def _load_fields(json_val: Any) -> List[Dict[str, Any]]:
    """从 custom_fields_json (JSON字段或JSON字符串) 中提取 customField 列表。"""
    if isinstance(json_val, str):
        try:
            json_val = json.loads(json_val)
        except (TypeError, ValueError):
            return []
    fields = json_val if isinstance(json_val, list) else []
    return [f for f in fields if isinstance(f, dict)]


def _field_id(field: Dict[str, Any]) -> str:
    return str(field.get("customFieldId") or field.get("customfieldId") or "").strip()


def _titles(field: Dict[str, Any]) -> Iterable[str]:
    for value in field.get("value") or []:
        if isinstance(value, dict) and value.get("title"):
            yield str(value["title"]).strip()


def _parse_cascading(fields: List[Dict[str, Any]], target_id: str) -> List[Optional[str]]:
    """解析级联字段，按 '/' 拆分，返回最多 3 级。"""
    parts: List[str] = []
    for field in fields:
        if _field_id(field) != target_id:
            continue
        for title in _titles(field):
            for part in title.split("/"):
                p = part.strip()
                if p and p not in parts:
                    parts.append(p)
    result: List[Optional[str]] = [None, None, None]
    for i, p in enumerate(parts[:3]):
        result[i] = p
    return result


def _column_names() -> set:
    """返回 program_issue_detail 当前所有列名。"""
    return {c["name"] for c in inspect(engine).get_columns("program_issue_detail")}


def _print_column_state() -> None:
    cols = sorted(inspect(engine).get_columns("program_issue_detail"), key=lambda c: c["name"])
    print(f"[列状态] program_issue_detail 共 {len(cols)} 列")
    for c in cols:
        print(f"  {c['name']}")


def run_ddl(dry_run: bool) -> bool:
    """执行 DDL 变更，返回是否有变更。"""
    existing = _column_names()
    changed = False

    with engine.begin() as conn:
        # 1. 重命名列
        for old_name, new_name in RENAME_MAP.items():
            if old_name in existing and new_name not in existing:
                stmt = f"ALTER TABLE program_issue_detail RENAME COLUMN {old_name} TO {new_name}"
                print(f"[DDL] {'[DRY-RUN] ' if dry_run else ''}{stmt}")
                if not dry_run:
                    conn.execute(text(stmt))
                existing.discard(old_name)
                existing.add(new_name)
                changed = True
            else:
                status = "已跳过（新名列已存在）" if new_name in existing else "已跳过（旧名列不存在）"
                print(f"[DDL] {old_name} -> {new_name}: {status}")

        # 2. 删除列
        for col in DROP_COLUMNS:
            if col in existing:
                stmt = f"ALTER TABLE program_issue_detail DROP COLUMN {col}"
                print(f"[DDL] {'[DRY-RUN] ' if dry_run else ''}{stmt}")
                if not dry_run:
                    conn.execute(text(stmt))
                changed = True

        # 3. 新增列
        for col, col_type in NEW_COLUMNS.items():
            if col not in existing:
                stmt = f"ALTER TABLE program_issue_detail ADD COLUMN {col} {col_type}"
                print(f"[DDL] {'[DRY-RUN] ' if dry_run else ''}{stmt}")
                if not dry_run:
                    conn.execute(text(stmt))
                changed = True

    if dry_run:
        print("[DDL] dry-run 完成，未实际变更数据库。")
    else:
        print("[DDL] 变更完成。")

    return changed


def backfill(limit: Optional[int], dry_run: bool, batch_size: int = 500) -> None:
    """从 custom_fields_json 回填 vehicle_* 和 problem_note_info_* 字段。

    使用原始 SQL 读写，避免 ORM 列名与 DB 不一致的问题（迁移前后均可运行）。
    """
    session = SessionLocal()
    # 使用原始 SQL 查询，仅读取 id + custom_fields_json
    sql = "SELECT id, custom_fields_json FROM program_issue_detail ORDER BY id"
    if limit:
        sql += f" LIMIT {limit}"

    try:
        result = session.execute(text(sql))
        rows = result.fetchall()

        scanned = 0
        updates = []
        for row_id, cfs_json in rows:
            scanned += 1
            fields = _load_fields(cfs_json)
            if not fields:
                continue

            vehicle = _parse_cascading(fields, VEHICLE_FIELD_ID)
            note_info = _parse_cascading(fields, PROBLEM_NOTE_INFO_FIELD_ID)

            if vehicle[0] is None and vehicle[1] is None and \
               note_info[0] is None and note_info[1] is None and note_info[2] is None:
                continue

            v1 = vehicle[0] or ""
            v2 = vehicle[1] or ""
            n1 = note_info[0] or ""
            n2 = note_info[1] or ""
            n3 = note_info[2] or ""

            if len(updates) < 3 or len(updates) % 200 == 0:
                print(f"  [#{row_id}] vehicle=({v1 or '-'}, {v2 or '-'}) "
                      f"note_info=({n1 or '-'}, {n2 or '-'}, {n3 or '-'})")

            update_sql = (
                "UPDATE program_issue_detail SET "
                f"vehicle_1 = :v1, vehicle_2 = :v2, "
                f"problem_note_info_1 = :n1, problem_note_info_2 = :n2, problem_note_info_3 = :n3 "
                "WHERE id = :rid"
            )
            updates.append({
                "sql": update_sql,
                "params": {"v1": v1, "v2": v2, "n1": n1, "n2": n2, "n3": n3, "rid": row_id},
            })

        if dry_run:
            session.rollback()
        else:
            # 批量执行 UPDATE
            updated = 0
            for i, upd in enumerate(updates):
                session.execute(text(upd["sql"]), upd["params"])
                updated += 1
                if i > 0 and i % batch_size == 0:
                    session.commit()
                    print(f"  已提交 {updated} 行...")
            session.commit()

        print(f"[回填] 扫描 {scanned} 条，需更新 {len(updates)} 条，模式={'dry-run' if dry_run else '写入'}")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ddl-only", action="store_true", help="仅执行 DDL，不回填数据")
    args = parser.parse_args()

    print("=" * 60)
    print("[开始] 变更前列状态：")
    _print_column_state()

    print("\n[步骤1] 执行 DDL 变更...")
    run_ddl(args.dry_run)

    if not args.dry_run:
        print("\n[变更后] 列状态：")
        _print_column_state()

    if args.ddl_only:
        print("[完成] 仅执行 DDL，跳过数据回填。")
        return

    print("\n[步骤2] 回填 vehicle + problem_note_info 数据...")
    backfill(args.limit, args.dry_run)

    print("\n[完成]")


if __name__ == "__main__":
    main()
