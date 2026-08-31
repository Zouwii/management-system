#!/usr/bin/env python3
"""Run one recoverable, observable full refresh of the benti workhour tables.

This is intentionally a CLI-only maintenance operation.  It is not registered as
an HTTP route and must be started explicitly by an operator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from sqlalchemy import text

# Allow direct execution as ``python scripts/run_benti_full_update.py``.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from base.api_monitor import BJ_TZ, enter_full_sync_mode, leave_full_sync_mode, monitor
from base.config.service import get_config_projectids
from base.db.engine import SessionLocal
from base.db.orm import Config, UserCharacter
from base.dingtalk_client import get_valid_access_token
from base.projects.task_service import query_project_tasks_service, query_user_tasks_service
from base.sync.lock import LOCK_BENTI, acquire_update_lock, release_update_lock
from base.sync.task_sync import (
    DEFAULT_DB_COMMIT_BATCH_SIZE,
    DEFAULT_SCENARIO_FIELD_CONFIG_ID,
    DEFAULT_WORKHOUR_FIELD_ID,
    ISSUE_SCENARIO_FIELD_CONFIG_ID,
    _extract_detail_item,
    _format_dt_for_tql_utc,
    _get_business_type_tag_mapping,
    _get_task_flow_status_mapping,
    _sync_one_detail_to_b_and_c,
    _sync_one_issue_detail,
    _upsert_config_value,
    sync_project_tasks_to_db,
)


TABLES = (
    "project_tasks",
    "project_task_details",
    "project_task_overdue_details",
    "program_issue",
    "program_issue_detail",
)
DELETE_ORDER = (
    "project_task_overdue_details",
    "project_task_details",
    "program_issue_detail",
    "project_tasks",
    "program_issue",
)
RUNTIME_DIR = BACKEND_DIR / "runtime"
STATE_PATH = RUNTIME_DIR / "benti_full_update_state.json"


def _now() -> str:
    return datetime.now(BJ_TZ).isoformat()


def _write_state(state: Dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(temp_path, STATE_PATH)


def _update_state(state: Dict[str, Any], **changes: Any) -> None:
    state.update(changes)
    state["updatedAt"] = _now()
    _write_state(state)


def _print(message: str) -> None:
    print(f"[{_now()}] {message}", flush=True)


def _table_counts() -> Dict[str, int]:
    session = SessionLocal()
    try:
        return {
            table: int(session.execute(text(f"SELECT COUNT(*) FROM `{table}`")).scalar() or 0)
            for table in TABLES
        }
    finally:
        session.close()


def _config_value(key: str) -> str | None:
    session = SessionLocal()
    try:
        row = session.query(Config).filter(Config.type_ == key).first()
        return str(row.value) if row else None
    finally:
        session.close()


def _backup_name(run_id: str, table: str) -> str:
    safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch == "_")
    return f"fullbak_{safe_run_id}_{table}"


def _create_backups(run_id: str) -> Dict[str, str]:
    backups = {table: _backup_name(run_id, table) for table in TABLES}
    session = SessionLocal()
    try:
        for source, backup in backups.items():
            exists = int(session.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = :name"
            ), {"name": backup}).scalar() or 0)
            if exists:
                raise RuntimeError(f"backup table already exists: {backup}")
            session.execute(text(f"CREATE TABLE `{backup}` LIKE `{source}`"))
            session.execute(text(f"INSERT INTO `{backup}` SELECT * FROM `{source}`"))
            session.commit()
            _print(f"backup {source} -> {backup}")
        return backups
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _clear_tables() -> None:
    session = SessionLocal()
    try:
        for table in DELETE_ORDER:
            session.execute(text(f"DELETE FROM `{table}`"))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _restore_backups(backups: Dict[str, str]) -> None:
    session = SessionLocal()
    try:
        for table in DELETE_ORDER:
            session.execute(text(f"DELETE FROM `{table}`"))
        for table in TABLES:
            session.execute(text(f"INSERT INTO `{table}` SELECT * FROM `{backups[table]}`"))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _api_baseline() -> Dict[str, int]:
    monitor._flush_batch()
    session = SessionLocal()
    try:
        row = session.execute(text("SELECT COALESCE(MAX(id), 0), COUNT(*) FROM api_call_logs")).one()
        return {"maxId": int(row[0] or 0), "count": int(row[1] or 0)}
    finally:
        session.close()


def _api_usage_after(max_id: int) -> Dict[str, Any]:
    monitor._flush_batch()
    session = SessionLocal()
    try:
        rows = session.execute(text(
            "SELECT source, endpoint, status, COUNT(*) calls "
            "FROM api_call_logs WHERE id > :max_id "
            "GROUP BY source, endpoint, status ORDER BY source, endpoint, status"
        ), {"max_id": int(max_id)}).all()
        breakdown = [
            {"source": row[0], "endpoint": row[1], "status": int(row[2]), "calls": int(row[3])}
            for row in rows
        ]
        return {
            "total": sum(item["calls"] for item in breakdown),
            "errors": sum(item["calls"] for item in breakdown if item["status"] >= 400),
            "breakdown": breakdown,
        }
    finally:
        session.close()


def _members() -> list[str]:
    session = SessionLocal()
    try:
        # 本体全量只覆盖导航组和对接组；算法组只参与工作日耗时，
        # 不得作为本体项目查询或明细写入的成员范围。
        rows = (
            session.query(UserCharacter.user_id)
            .filter(UserCharacter.team_code.in_(("NAV", "INTEGRATION")))
            .order_by(UserCharacter.user_id)
            .all()
        )
        return [str(row[0]).strip() for row in rows if row and str(row[0] or "").strip()]
    finally:
        session.close()


def _query_member_list(
    access_token: str,
    user_id: str,
    project_id: str,
    threshold: str,
    attempts: int = 3,
) -> Tuple[Dict[str, Any], int]:
    payload = {
        "userId": user_id,
        "projectId": project_id,
        "access_token": access_token,
        "query": "(updated >= '{}')".format(_format_dt_for_tql_utc(datetime.fromisoformat(threshold))),
        "maxResults": 500,
        "maxPages": 200,
        "force_refresh": True,
        "retries": 2,
    }
    last_result: Dict[str, Any] = {}
    for attempt in range(1, attempts + 1):
        last_result = query_project_tasks_service(payload)
        if last_result.get("success"):
            return last_result, attempt
        _print(f"list user={user_id} attempt {attempt}/{attempts} failed: {last_result.get('error')}")
    return last_result, attempts


def _detail_request(
    access_token: str,
    project_id: str,
    kind: str,
    executor_id: str,
    task_id: str,
) -> Dict[str, Any]:
    result = query_user_tasks_service({
        "userId": executor_id,
        "taskId": task_id,
        "projectId": project_id,
        "access_token": access_token,
        "force_refresh": True,
    })
    item = _extract_detail_item(result) if result.get("success") else None
    return {
        "success": bool(result.get("success") and isinstance(item, dict)),
        "kind": kind,
        "executorId": executor_id,
        "taskId": task_id,
        "item": item,
        "error": result.get("error") if not result.get("success") else ("empty detail" if not item else ""),
    }


def _fetch_details(
    access_token: str,
    project_id: str,
    specs: list[Tuple[str, str, str]],
    state: Dict[str, Any],
    workers: int = 5,
    max_attempts: int = 3,
) -> list[Dict[str, Any]]:
    pending = list(specs)
    successes: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    last_failures: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

    for attempt in range(1, max_attempts + 1):
        if not pending:
            break
        _print(f"detail round {attempt}/{max_attempts}: pending={len(pending)}")
        next_pending: list[Tuple[str, str, str]] = []
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
            futures = {
                pool.submit(_detail_request, access_token, project_id, kind, executor, task):
                (kind, executor, task)
                for kind, executor, task in pending
            }
            completed_in_round = 0
            for future in as_completed(futures):
                key = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "success": False,
                        "kind": key[0],
                        "executorId": key[1],
                        "taskId": key[2],
                        "item": None,
                        "error": repr(exc),
                    }
                if result.get("success"):
                    successes[key] = result
                    last_failures.pop(key, None)
                else:
                    next_pending.append(key)
                    last_failures[key] = result
                completed_in_round += 1
                total_done = len(successes)
                if completed_in_round % 100 == 0:
                    _update_state(
                        state,
                        progress={
                            "phase": "fetching_details",
                            "detailRound": attempt,
                            "detailFetched": total_done,
                            "detailTotal": len(specs),
                            "detailPending": len(specs) - total_done,
                        },
                    )
        pending = next_pending

    if pending:
        sample = [last_failures[key] for key in pending[:20]]
        raise RuntimeError(f"{len(pending)} task details failed after {max_attempts} rounds: {sample}")
    return [successes[key] for key in specs]


def _write_rebuilt_tables(
    project_id: str,
    tasks: list[Dict[str, Any]],
    details: list[Dict[str, Any]],
) -> Dict[str, int]:
    query_result = {
        "success": True,
        "data": {"dingtalk": {"result": tasks}},
        "meta": {"source": "benti_full_deduplicated"},
    }
    a_result = sync_project_tasks_to_db({
        "projectId": project_id,
        "scenarioFieldConfigIds": [DEFAULT_SCENARIO_FIELD_CONFIG_ID, ISSUE_SCENARIO_FIELD_CONFIG_ID],
    }, query_result=query_result)
    if not a_result.get("success"):
        raise RuntimeError(f"failed to rebuild A tables: {a_result.get('error')}")

    field_id = str(os.getenv("TB_TOOL_BT_WORKHOUR_FIELD_ID") or DEFAULT_WORKHOUR_FIELD_ID)
    business_mapping = _get_business_type_tag_mapping()
    status_mapping = _get_task_flow_status_mapping()
    session = SessionLocal()
    written = {"dev": 0, "issue": 0}
    pending_commit = 0
    try:
        for result in details:
            item = result["item"]
            if result["kind"] == "dev":
                _sync_one_detail_to_b_and_c(
                    session,
                    executor_id=result["executorId"],
                    task_id=result["taskId"],
                    project_id=project_id,
                    item=item,
                    field_id=field_id,
                    now=datetime.now(timezone.utc),
                    business_type_mapping=business_mapping,
                    task_flow_status_mapping=status_mapping,
                    write_b=True,
                    write_c=True,
                )
            else:
                _sync_one_issue_detail(
                    session,
                    executor_id=result["executorId"],
                    task_id=result["taskId"],
                    project_id=project_id,
                    item=item,
                    field_id=field_id,
                    now=datetime.now(timezone.utc),
                    business_type_mapping=business_mapping,
                )
            written[result["kind"]] += 1
            pending_commit += 1
            if pending_commit >= DEFAULT_DB_COMMIT_BATCH_SIZE:
                session.commit()
                pending_commit = 0
        if pending_commit:
            session.commit()
        return written
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run(run_id: str, lookback_days: int) -> int:
    owner = f"benti_full@{run_id}"
    state: Dict[str, Any] = {
        "runId": run_id,
        "status": "starting",
        "startedAt": _now(),
        "updatedAt": _now(),
        "lookbackDays": lookback_days,
        "pid": os.getpid(),
        "progress": {},
    }
    _write_state(state)

    lock_acquired = False
    bypass_entered = False
    cleared = False
    backups: Dict[str, str] = {}
    previous_switch = _config_value("daily_sync_enabled")
    previous_last_update = _config_value("last_update_time")

    try:
        lock = acquire_update_lock(LOCK_BENTI, owner, ttl_sec=60 * 60 * 48)
        if not lock.get("ok"):
            raise RuntimeError(lock.get("error", "failed to acquire benti lock"))
        lock_acquired = True

        _upsert_config_value("daily_sync_enabled", "true")
        enter_full_sync_mode()
        bypass_entered = True

        baseline = _api_baseline()
        counts_before = _table_counts()
        members = _members()
        project_ids = get_config_projectids() or {}
        project_id = str(next(iter(project_ids.values())) or "").strip()
        if not project_id:
            raise RuntimeError("missing projectId from config")
        if not members:
            raise RuntimeError("no users found in user_character")

        _update_state(
            state,
            status="fetching_lists",
            apiBaseline=baseline,
            countsBefore=counts_before,
            memberCount=len(members),
            projectId=project_id,
            previousSyncSwitch=previous_switch,
            previousLastUpdateTime=previous_last_update,
        )
        threshold = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        _update_state(state, fullSyncThreshold=threshold)
        token_result = get_valid_access_token({})
        if not token_result.get("ok"):
            raise RuntimeError(token_result.get("error", "failed to get DingTalk access token"))
        access_token = str(token_result["access_token"])

        tasks_by_id: Dict[str, Dict[str, Any]] = {}
        list_results: Dict[str, Any] = {}
        allowed_scenarios = {DEFAULT_SCENARIO_FIELD_CONFIG_ID, ISSUE_SCENARIO_FIELD_CONFIG_ID}
        _print(f"fetching lists: members={len(members)} project={project_id} threshold={threshold}")
        for index, user_id in enumerate(members, start=1):
            _print(f"list member {index}/{len(members)} user={user_id}")
            result, attempts = _query_member_list(access_token, user_id, project_id, threshold)
            if not result.get("success"):
                raise RuntimeError(f"member list failed user={user_id}: {result.get('error')}")
            ding = (result.get("data") or {}).get("dingtalk") or {}
            rows = ding.get("result") if isinstance(ding.get("result"), list) else []
            accepted = 0
            for item in rows:
                if not isinstance(item, dict):
                    continue
                scenario_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
                task_id = str(item.get("taskId") or "").strip()
                if scenario_id not in allowed_scenarios or not task_id:
                    continue
                tasks_by_id.setdefault(task_id, item)
                accepted += 1
            list_results[user_id] = {
                "attempts": attempts,
                "pages": int((result.get("meta") or {}).get("page_count") or 0),
                "fetched": len(rows),
                "accepted": accepted,
                "uniqueTotal": len(tasks_by_id),
            }
            _update_state(
                state,
                progress={
                    "completedMembers": index,
                    "totalMembers": len(members),
                    "currentMember": user_id,
                    "currentIndex": index,
                    "phase": "fetching_lists",
                    "uniqueTasks": len(tasks_by_id),
                },
                listResults=list_results,
                apiUsage=_api_usage_after(baseline["maxId"]),
            )

        # The benti database is owned exclusively by the two benti teams.  A
        # project list can contain tasks assigned to algorithm-team users (or
        # other collaborators), so filter the shared project result before
        # rebuilding either the list tables or the detail tables.
        allowed_executors = set(members)
        filtered_tasks_by_id: Dict[str, Dict[str, Any]] = {}
        skipped_executors = {"dev": 0, "issue": 0}
        for task_id, item in tasks_by_id.items():
            scenario_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
            executor_id = str(item.get("executorId") or "").strip()
            kind = "dev" if scenario_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID else "issue"
            if not executor_id or executor_id not in allowed_executors:
                skipped_executors[kind] += 1
                continue
            filtered_tasks_by_id[task_id] = item
        tasks_by_id = filtered_tasks_by_id

        detail_specs: list[Tuple[str, str, str]] = []
        for task_id, item in tasks_by_id.items():
            scenario_id = str(item.get("scenarioFieldConfigId") or item.get("scenariofieldconfigId") or "")
            executor_id = str(item.get("executorId") or "").strip()
            if scenario_id == DEFAULT_SCENARIO_FIELD_CONFIG_ID:
                detail_specs.append(("dev", executor_id, task_id))
            elif scenario_id == ISSUE_SCENARIO_FIELD_CONFIG_ID:
                detail_specs.append(("issue", executor_id, task_id))

        detail_specs = list(dict.fromkeys(detail_specs))
        _update_state(
            state,
            status="fetching_details",
            progress={
                "phase": "fetching_details",
                "detailFetched": 0,
                "detailTotal": len(detail_specs),
                "detailPending": len(detail_specs),
            },
            uniqueTaskCount=len(tasks_by_id),
            detailSpecCount=len(detail_specs),
            skippedExecutors=skipped_executors,
        )
        details = _fetch_details(
            access_token,
            project_id,
            detail_specs,
            state,
        )

        # Only after all remote data is complete do we touch the live five tables.
        _update_state(state, status="backing_up", progress={"phase": "backing_up"})
        backups = _create_backups(run_id)
        _update_state(state, backupTables=backups, status="rebuilding", progress={"phase": "clearing"})
        _clear_tables()
        cleared = True
        _update_state(state, progress={"phase": "writing", "detailTotal": len(details)})
        written = _write_rebuilt_tables(project_id, list(tasks_by_id.values()), details)

        completed_at = datetime.now(BJ_TZ).isoformat()
        _upsert_config_value("last_update_time", completed_at)
        usage = _api_usage_after(baseline["maxId"])
        counts_after = _table_counts()
        _update_state(
            state,
            status="completed",
            completedAt=completed_at,
            countsAfter=counts_after,
            apiUsage=usage,
            written=written,
            failures=[],
        )
        _print(f"completed: api_calls={usage['total']} counts={counts_after}")
        return 0
    except BaseException as exc:
        _print(f"FAILED: {exc!r}")
        restore_error = ""
        if cleared and backups:
            try:
                _update_state(state, status="restoring", error=str(exc))
                _restore_backups(backups)
                if previous_last_update is not None:
                    _upsert_config_value("last_update_time", previous_last_update)
                _print("original five tables restored from backup")
            except Exception as restore_exc:
                restore_error = repr(restore_exc)
                _print(f"RESTORE FAILED: {restore_error}")
        _update_state(
            state,
            status="failed",
            failedAt=_now(),
            error=repr(exc),
            traceback=traceback.format_exc(),
            restoreError=restore_error,
            restored=bool(cleared and backups and not restore_error),
            apiUsage=_api_usage_after((state.get("apiBaseline") or {}).get("maxId", 0)),
            countsAfterFailure=_table_counts(),
        )
        return 1
    finally:
        if bypass_entered:
            leave_full_sync_mode()
        if previous_switch is not None:
            _upsert_config_value("daily_sync_enabled", previous_switch)
        if lock_acquired:
            release_update_lock(LOCK_BENTI, owner)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=datetime.now(BJ_TZ).strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--lookback-days", type=int, default=365)
    args = parser.parse_args()
    if args.lookback_days < 1:
        parser.error("--lookback-days must be positive")
    return run(args.run_id, args.lookback_days)


if __name__ == "__main__":
    sys.exit(main())
