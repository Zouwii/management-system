#!/usr/bin/env python3
"""从 program_issue_detail 的 customFields/raw_json 回填问题标签层级。

只解析接口返回的实际标签，不做关键词推断：
  问题类型字段 -> problem_type_1/2
  原因字段     -> cause_level_1/2/3

用法：
  python scripts/backfill_program_issue_label_levels.py --dry-run
  python scripts/backfill_program_issue_label_levels.py
  python scripts/backfill_program_issue_label_levels.py --limit 100
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import inspect, text

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from base.db.engine import SessionLocal, engine  # noqa: E402
from base.db.orm import ProgramIssueDetail  # noqa: E402


PROBLEM_TYPE_FIELD_ID = "67c56f477ed2b4b7bbd0cd69"
SOFTWARE_VERSION_FIELD_ID = "65a7be8938685843bf1c7d83"
# 原因字段曾按场景/版本拆成多个 customField；它们的 value 结构相同，都要解析。
CAUSE_FIELD_IDS = {
    "67c571aa5aed540b545e208c",
    "67c571c89a5dc6dbb8511d99",
    "67c5715253aacbf8cf267e81",
    "67c571d86db6f1be2bf2f88f",
}


def _as_fields(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        value = value.get("customFields") or value.get("customfields") or []
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    return []


def _load_fields(custom_fields_json: Any, raw_json: Optional[str]) -> List[Dict[str, Any]]:
    fields = _as_fields(custom_fields_json)
    if fields:
        return fields
    try:
        return _as_fields(json.loads(raw_json or "{}"))
    except (TypeError, ValueError):
        return []


def _field_id(field: Dict[str, Any]) -> str:
    return str(field.get("customFieldId") or field.get("customfieldId") or field.get("cfId") or "")


def _titles(field: Dict[str, Any]) -> Iterable[str]:
    for value in field.get("value") or []:
        if isinstance(value, dict) and value.get("title"):
            yield str(value["title"]).strip()


def _levels(fields: List[Dict[str, Any]], target_ids) -> List[Optional[str]]:
    paths = []
    for field in fields:
        if _field_id(field) not in target_ids:
            continue
        for title in _titles(field):
            parts = [part.strip() for part in title.split("/") if part.strip()]
            if parts:
                paths.append(parts[:3])

    # 同一任务可能同时保留旧版和新版原因字段，优先使用层级更完整的路径。
    if paths:
        paths = [max(paths, key=len)]

    result: List[Optional[str]] = []
    for index in range(3):
        values = []
        for path in paths:
            if index < len(path) and path[index] not in values:
                values.append(path[index])
        result.append("; ".join(values) if values else None)
    return result


def _value_titles(fields: List[Dict[str, Any]], target_id: str) -> Optional[str]:
    titles = []
    for field in fields:
        if _field_id(field) != target_id:
            continue
        for title in _titles(field):
            if title not in titles:
                titles.append(title)
    return "; ".join(titles) if titles else None


def ensure_columns() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("program_issue_detail")}
    definitions = {
        "problem_type_1": "VARCHAR(128)",
        "problem_type_2": "VARCHAR(128)",
        "cause_level_1": "VARCHAR(128)",
        "cause_level_2": "VARCHAR(128)",
        "cause_level_3": "VARCHAR(256)",
        "software_version": "VARCHAR(128)",
    }
    with engine.begin() as connection:
        for name, column_type in definitions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE program_issue_detail ADD COLUMN {name} {column_type}"))


def backfill(limit: Optional[int], dry_run: bool, batch_size: int = 500) -> None:
    ensure_columns()
    session = SessionLocal()
    query = session.query(ProgramIssueDetail).order_by(ProgramIssueDetail.id)
    if limit:
        query = query.limit(limit)
    # 先取出结果，避免 MySQL 流式游标在中途 commit 后被关闭，导致只处理首个 batch。
    rows = query.all()

    scanned = updated = with_labels = 0
    try:
        for row in rows:
            scanned += 1
            fields = _load_fields(row.custom_fields_json, row.raw_json)
            problem = _levels(fields, PROBLEM_TYPE_FIELD_ID)
            cause = _levels(fields, CAUSE_FIELD_IDS)
            software_version = _value_titles(fields, SOFTWARE_VERSION_FIELD_ID)
            if any(problem) or any(cause):
                with_labels += 1

            changed = (
                [row.problem_type_1, row.problem_type_2] != problem[:2]
                or [row.cause_level_1, row.cause_level_2, row.cause_level_3] != cause
                or row.software_version != software_version
            )
            if changed:
                row.problem_type_1, row.problem_type_2 = problem[0], problem[1]
                row.cause_level_1, row.cause_level_2, row.cause_level_3 = cause
                row.software_version = software_version
                updated += 1
            if not dry_run and scanned % batch_size == 0:
                session.commit()

        if dry_run:
            session.rollback()
        else:
            session.commit()
        print(f"扫描 {scanned} 条，包含标签 {with_labels} 条，需更新 {updated} 条，模式={'dry-run' if dry_run else '写入'}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(args.limit, args.dry_run)


if __name__ == "__main__":
    main()
