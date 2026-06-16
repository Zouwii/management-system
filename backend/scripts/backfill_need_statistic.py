"""回填三张 detail 表的 need_statistic 字段。

从 custom_fields_json 中提取 NEED_STATISTIC_CUSTOMFIELD_ID
对应的 是/否 值，写入 need_statistic 列。

用法:  cd backend && poetry run python3 scripts/backfill_need_statistic.py
"""

import json
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, '.')

from base.db.engine import SessionLocal
from base.db.orm import ProjectTaskDetail, ProgramIssueDetail, ProjectTaskOverdueDetail

NEED_STATISTIC_CUSTOMFIELD_ID = '667a65e618aebd88f98d4896'


def _extract_need_statistic_from_cf(custom_fields: Any) -> Optional[str]:
    if not isinstance(custom_fields, list):
        return None
    for cf in custom_fields:
        if not isinstance(cf, dict):
            continue
        cfid = str(cf.get('customFieldId') or cf.get('customfieldId') or '').strip()
        if cfid != NEED_STATISTIC_CUSTOMFIELD_ID:
            continue
        values = cf.get('value') or []
        if isinstance(values, list) and values:
            first = values[0]
            if isinstance(first, dict):
                title = str(first.get('title') or '').strip()
                if title in ('是', '否'):
                    return title
        break
    return None


def _extract_need_statistic_from_raw(raw_json: Any) -> Optional[str]:
    if not raw_json:
        return None
    try:
        obj = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
    except (json.JSONDecodeError, TypeError):
        return None
    cfs = obj.get('customFields') or obj.get('customfields') or []
    return _extract_need_statistic_from_cf(cfs)


def backfill_table(model, label: str) -> Dict[str, int]:
    session = SessionLocal()
    stats = {'found': 0, 'not_found': 0, 'updated': 0}
    try:
        rows = session.query(model).filter(model.need_statistic == None).all()
        print(f'[{label}] NULL 行: {len(rows)}')
        for row in rows:
            val = None
            if row.custom_fields_json is not None:
                val = _extract_need_statistic_from_cf(row.custom_fields_json)
            if val is None and getattr(row, 'raw_json', None) is not None:
                val = _extract_need_statistic_from_raw(row.raw_json)
            if val is not None:
                row.need_statistic = val
                stats['found'] += 1
            else:
                stats['not_found'] += 1
        session.commit()
        stats['updated'] = stats['found']
        print(f'  提取成功: {stats["found"]}  无数据: {stats["not_found"]}  已更新: {stats["updated"]}')
    except Exception as e:
        session.rollback()
        print(f'  错误: {e}')
    finally:
        session.close()
    return stats


def main():
    print('=' * 60)
    print('need_statistic 字段回填脚本')
    print('=' * 60)
    results = {}
    results['ProjectTaskDetail'] = backfill_table(ProjectTaskDetail, 'ProjectTaskDetail')
    results['ProgramIssueDetail'] = backfill_table(ProgramIssueDetail, 'ProgramIssueDetail')
    results['ProjectTaskOverdueDetail'] = backfill_table(ProjectTaskOverdueDetail, 'ProjectTaskOverdueDetail')
    print()
    print('=' * 60)
    print('汇总:')
    total = sum(r['updated'] for r in results.values())
    total_not = sum(r['not_found'] for r in results.values())
    for name, r in results.items():
        print(f'  {name}: 更新 {r["updated"]} 行, 无数据 {r["not_found"]} 行')
    print(f'  总计更新: {total} 行 (无数据: {total_not} 行)')
    print('=' * 60)

if __name__ == '__main__':
    main()
