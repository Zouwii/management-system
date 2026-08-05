#!/usr/bin/env python3
"""临时回填 onsite B 表的钉钉创建/更新时间。

来源优先级：A 表 raw_json.created/updated，缺失时使用 A 表已解析的 ding_created/ding_updated。
按 task_id 更新 B 表的全部对应明细，不调用外部接口。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime

from base.db.engine import OnsiteSessionLocal
from base.db.orm import OnsiteProblemDetail, OnsiteProblemTask


def parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="从 onsite A 表回填 B 表钉钉创建/更新时间")
    parser.add_argument("--dry-run", action="store_true", help="只统计和预览，不写数据库")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条 A 表记录，0 表示全部")
    args = parser.parse_args()

    source_session = OnsiteSessionLocal()
    target_session = OnsiteSessionLocal()
    scanned = updated = missing = no_time = 0
    try:
        query = source_session.query(OnsiteProblemTask).order_by(OnsiteProblemTask.id)
        if args.limit > 0:
            query = query.limit(args.limit)
        sources = query.all()
        targets_by_task = defaultdict(list)
        for target in target_session.query(OnsiteProblemDetail).all():
            targets_by_task[target.task_id].append(target)
        for source in sources:
            scanned += 1
            payload = {}
            if source.raw_json:
                try:
                    payload = json.loads(source.raw_json)
                except (TypeError, ValueError):
                    payload = {}
            created = parse_time(payload.get("created")) or source.ding_created
            updated_time = parse_time(payload.get("updated")) or source.ding_updated
            if not created and not updated_time:
                no_time += 1
                continue
            targets = targets_by_task.get(source.task_id, [])
            if not targets:
                missing += 1
                continue
            if not args.dry_run:
                for target in targets:
                    target.ding_created = created
                    target.ding_updated = updated_time
            updated += len(targets)
            if args.dry_run and updated <= 10:
                print(f"[DRY-RUN] task={source.task_id} created={created} updated={updated_time} rows={len(targets)}")
        if not args.dry_run:
            target_session.commit()
        print(f"[DONE] A扫描={scanned}, B更新={updated}, 无B记录={missing}, 无时间={no_time}, dry_run={args.dry_run}")
    except Exception:
        target_session.rollback()
        raise
    finally:
        source_session.close()
        target_session.close()


if __name__ == "__main__":
    main()
