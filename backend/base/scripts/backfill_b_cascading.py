#!/usr/bin/env python3
"""回填 project_task_details 表的级联三列（project_category_1 / vehicle_type_2 / project_name_3）。"""

import json
import sys
import os

# 确保 backend 目录在 sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

from base.db.engine import SessionLocal
from base.db.orm import ProjectTaskDetail

CASCADING_FIELD_ID = "665ee4b45b46f34b3e045af2"


def parse_cascading(raw_json_str: str) -> tuple:
    """从 raw_json 解析级联三级字段，返回 (cat, vehicle, name)。"""
    try:
        data = json.loads(raw_json_str)
    except Exception:
        return None, None, None

    cfs = data.get("customFields") or data.get("customfields") or []
    if not isinstance(cfs, list):
        return None, None, None

    for cf in cfs:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get("customFieldId") or cf.get("customfieldId") or "").strip()
        if cfid != CASCADING_FIELD_ID:
            continue
        values = cf.get("value") or []
        if not isinstance(values, list) or not values:
            return None, None, None
        first = values[0]
        if not isinstance(first, dict):
            return None, None, None
        title = str(first.get("title") or "").strip()
        if not title:
            return None, None, None
        parts = [p.strip() for p in title.split("/")]
        return (
            parts[0] if len(parts) >= 1 and parts[0] else None,
            parts[1] if len(parts) >= 2 and parts[1] else None,
            parts[2] if len(parts) >= 3 and parts[2] else None,
        )

    return None, None, None


def main():
    session = SessionLocal()
    try:
        # 查 raw_json 非空且三个级联列有空的行
        rows = (
            session.query(ProjectTaskDetail)
            .filter(ProjectTaskDetail.raw_json != None)  # noqa: E711
            .filter(ProjectTaskDetail.raw_json != "")
            .filter(ProjectTaskDetail.raw_json != "null")
            .filter(
                (ProjectTaskDetail.project_category_1 == None)  # noqa: E711
                | (ProjectTaskDetail.vehicle_type_2 == None)  # noqa: E711
                | (ProjectTaskDetail.project_name_3 == None)  # noqa: E711
            )
            .all()
        )

        print(f"[B 表] 待回填行数: {len(rows)}")

        updated = 0
        skipped = 0
        for row in rows:
            cat, vehicle, name = parse_cascading(row.raw_json)
            if cat is not None or vehicle is not None or name is not None:
                row.project_category_1 = cat
                row.vehicle_type_2 = vehicle
                row.project_name_3 = name
                updated += 1
            else:
                skipped += 1

            if updated % 500 == 0:
                session.commit()
                print(f"  已提交 {updated} 行...")

        session.commit()
        print(f"[B 表] 完成: 回填 {updated} 行, 跳过(无级联数据) {skipped} 行")

    except Exception as e:
        session.rollback()
        print(f"[B 表] 错误: {e}")
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
