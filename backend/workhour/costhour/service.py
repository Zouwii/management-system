"""工作日耗时统计核心服务：查询 + 聚合逻辑。"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError

from base.db.engine import AlgoSessionLocal, SessionLocal
from base.db.orm import (
    AlgoIssue,
    AlgoIssueDetail,
    AlgoTask,
    AlgoTaskDetail,
    ProgramIssue,
    ProgramIssueDetail,
    ProjectTask,
    ProjectTaskDetail,
    ProjectTaskOverdueDetail,
    UserCharacter as DbUserCharacter,
)

SH_TZ = ZoneInfo("Asia/Shanghai")

# 工作日耗时统计参与人员白名单
WHITELIST_USER_IDS = {
    "01195014075436361289",  # 邹宏睿 导航组
    "010408241117947540",    # 王睿   导航组
    "250124013220811839",    # 何鸿颉 导航组
    "2739002424650905",      # 何华   导航组
    "27274739521079424",     # 蒲曲   导航组
    "396813112226338830",    # 杨沅钋 导航组
    "234765171227529303",    # 沈旭东 对接组
    "011168364322856029",    # 李赫   对接组
    "02013312354020881768",  # 刘力璋 对接组
    "01183307230324910099",  # 戴宇庆 对接组
    # 算法组
    "0525436259671512",      # 刘丰
    "2464543025951000",      # 琚玲
    "555363695138848564",    # 高尔峰
    "22665556381168535",     # 邵京
    "2409506118778941",      # 庞涛
}

# 出勤表专用分组：不修改 ids.json，也不改变 user_character 的全局 team_id。
# 这些人员属于当前 ids.json 导航组，但不在导航统计白名单中。
ATTENDANCE_APPLICATION_USER_IDS = {
    "2108411066921750",      # 潘铮
    "265352386036276420",    # 郑世玉
    "495200335237410081",    # 钟昌郎
    "312542394537803309",    # 陈文斌
}
ATTENDANCE_PARTICIPANT_USER_IDS = WHITELIST_USER_IDS | ATTENDANCE_APPLICATION_USER_IDS
ATTENDANCE_NAV_USER_IDS = {
    "01195014075436361289", "010408241117947540", "250124013220811839",
    "2739002424650905", "27274739521079424", "396813112226338830",
}
ATTENDANCE_SERVO_USER_IDS = {
    "234765171227529303", "011168364322856029",
    "02013312354020881768", "01183307230324910099",
}
ATTENDANCE_ALGO_USER_IDS = {
    "0525436259671512", "2464543025951000", "555363695138848564",
    "22665556381168535", "2409506118778941",
}


def _to_utc_dt_safe(v: Any) -> Optional[datetime]:
    s = str(v or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SH_TZ).astimezone(timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def _team_name_static(team_id_value: Any) -> str:
    val = str(team_id_value or "").strip()
    if val == "0":
        return "导航组"
    if val == "1":
        return "对接组"
    if val == "2":
        return "算法组"
    if val == "3":
        return "应用组"
    return "未分组"


def _attendance_team_id(user_id: str, db_team_id: Any) -> str:
    """团队数据缺失时按统计名单配置兜底，避免出勤表出现未分组。"""
    tid = str(db_team_id or "").strip()
    if user_id in ATTENDANCE_APPLICATION_USER_IDS:
        return "3"
    if tid:
        return tid
    if user_id in ATTENDANCE_NAV_USER_IDS:
        return "0"
    if user_id in ATTENDANCE_SERVO_USER_IDS:
        return "1"
    if user_id in ATTENDANCE_ALGO_USER_IDS:
        return "2"
    return ""


def _resolve_time_range(payload: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime], Optional[str]]:
    """解析并校验时间参数，返回 (start_dt, end_dt, error)。"""
    start_raw = payload.get("start_time")
    end_raw = payload.get("end_time")
    start_dt = _to_utc_dt_safe(start_raw)
    end_dt = _to_utc_dt_safe(end_raw)
    if not start_dt or not end_dt:
        return None, None, "missing or invalid start_time/end_time"
    if start_dt > end_dt:
        return None, None, "start_time must be <= end_time"
    return start_dt, end_dt, None


def _query_workday_costhour_base(
    start_dt: datetime,
    end_dt: datetime,
) -> List[Dict[str, Any]]:
    """
    核心查询：三张明细表统一拉取，关联 user_character 获取团队信息。

    返回每行:
      { userId, userName, teamId, teamName, taskType, businessType,
        taskId, content, workdayCosthour }
    """
    session = SessionLocal()
    algo_session = AlgoSessionLocal()
    try:
        # ── 软件开发：B 表（本季度排期） ──
        b_rows = (
            session.query(
                ProjectTaskDetail.query_user_id,
                ProjectTaskDetail.workday_costhour,
                ProjectTaskDetail.need_statistic,
                ProjectTaskDetail.project_category_1,
                ProjectTaskDetail.task_id,
                ProjectTaskDetail.content,
                ProjectTaskDetail.scenario_field_config_id,
                ProjectTaskDetail.vehicle_type_2,
                ProjectTaskDetail.project_name_3,
            )
            .join(
                ProjectTask,
                and_(
                    ProjectTask.project_id == ProjectTaskDetail.project_id,
                    ProjectTask.task_id == ProjectTaskDetail.task_id,
                ),
            )
            .filter(ProjectTask.due_date != None)  # noqa: E711
            .filter(ProjectTask.due_date >= start_dt)
            .filter(ProjectTask.due_date <= end_dt)
            .all()
        )

        # ── 软件开发：C 表（逾期） ──
        c_rows = (
            session.query(
                ProjectTaskOverdueDetail.query_user_id,
                ProjectTaskOverdueDetail.workday_costhour,
                ProjectTaskOverdueDetail.need_statistic,
                ProjectTaskOverdueDetail.project_category_1,
                ProjectTaskOverdueDetail.task_id,
                ProjectTaskOverdueDetail.content,
                ProjectTaskOverdueDetail.scenario_field_config_id,
                ProjectTaskOverdueDetail.vehicle_type_2,
                ProjectTaskOverdueDetail.project_name_3,
            )
            .join(
                ProjectTask,
                and_(
                    ProjectTask.project_id == ProjectTaskOverdueDetail.project_id,
                    ProjectTask.task_id == ProjectTaskOverdueDetail.task_id,
                ),
            )
            .filter(ProjectTask.due_date != None)  # noqa: E711
            .filter(ProjectTask.due_date >= start_dt)
            .filter(ProjectTask.due_date <= end_dt)
            .all()
        )

        # ── 问题处理 ──
        issue_rows = (
            session.query(
                ProgramIssueDetail.query_user_id,
                ProgramIssueDetail.workday_costhour,
                ProgramIssueDetail.need_statistic,
                ProgramIssueDetail.project_category_1,
                ProgramIssueDetail.vehicle_type_2,
                ProgramIssueDetail.project_name_3,
                ProgramIssue.task_id,
                ProgramIssue.content,
            )
            .join(
                ProgramIssue,
                and_(
                    ProgramIssue.project_id == ProgramIssueDetail.project_id,
                    ProgramIssue.task_id == ProgramIssueDetail.task_id,
                ),
            )
            .filter(ProgramIssue.due_date != None)  # noqa: E711
            .filter(ProgramIssue.due_date >= start_dt)
            .filter(ProgramIssue.due_date <= end_dt)
            .all()
        )

        # 算法库是可选数据源；本地未建库时仍返回导航组/对接组数据。
        algo_task_rows = []
        algo_issue_rows = []
        try:
            # ── 算法开发：algo_task_details + algo_tasks ──
            algo_task_rows = (
                algo_session.query(
                    AlgoTaskDetail.query_user_id,
                    AlgoTaskDetail.workday_costhour,
                    AlgoTaskDetail.need_statistic,
                    AlgoTaskDetail.project_category_1,
                    AlgoTaskDetail.task_id,
                    AlgoTaskDetail.content,
                    AlgoTaskDetail.scenario_field_config_id,
                    AlgoTaskDetail.vehicle_type_2,
                    AlgoTaskDetail.project_name_3,
                )
                .join(
                    AlgoTask,
                    and_(
                        AlgoTask.project_id == AlgoTaskDetail.project_id,
                        AlgoTask.task_id == AlgoTaskDetail.task_id,
                    ),
                )
                .filter(AlgoTask.due_date != None)
                .filter(AlgoTask.due_date >= start_dt)
                .filter(AlgoTask.due_date <= end_dt)
                .all()
            )

            # ── 算法问题：algo_issue_details + algo_issues ──
            algo_issue_rows = (
                algo_session.query(
                    AlgoIssueDetail.query_user_id,
                    AlgoIssueDetail.workday_costhour,
                    AlgoIssueDetail.need_statistic,
                    AlgoIssueDetail.project_category_1,
                    AlgoIssueDetail.vehicle_type_2,
                    AlgoIssueDetail.project_name_3,
                    AlgoIssue.task_id,
                    AlgoIssue.content,
                )
                .join(
                    AlgoIssue,
                    and_(
                        AlgoIssue.project_id == AlgoIssueDetail.project_id,
                        AlgoIssue.task_id == AlgoIssueDetail.task_id,
                    ),
                )
                .filter(AlgoIssue.due_date != None)
                .filter(AlgoIssue.due_date >= start_dt)
                .filter(AlgoIssue.due_date <= end_dt)
                .all()
            )
        except SQLAlchemyError as e:
            algo_session.rollback()
            print(f"[workday_costhour] skip algo data: {e}")

        # ── 获取所有涉及的 user_id，批量查 team 信息 ──
        all_user_ids = set()
        for uid, *_ in b_rows:
            if uid:
                all_user_ids.add(str(uid).strip())
        for uid, *_ in c_rows:
            if uid:
                all_user_ids.add(str(uid).strip())
        for uid, *_ in issue_rows:
            if uid:
                all_user_ids.add(str(uid).strip())
        for uid, *_ in algo_task_rows:
            if uid:
                all_user_ids.add(str(uid).strip())
        for uid, *_ in algo_issue_rows:
            if uid:
                all_user_ids.add(str(uid).strip())

        user_map: Dict[str, Dict[str, Any]] = {}
        if all_user_ids:
            uc_rows = (
                session.query(DbUserCharacter)
                .filter(DbUserCharacter.user_id.in_(list(all_user_ids)))
                .all()
            )
            for uc in uc_rows:
                uid = str(getattr(uc, "user_id", "") or "").strip()
                if not uid:
                    continue
                user_map[uid] = {
                    "name": str(getattr(uc, "name", "") or uid),
                    "teamId": str(getattr(uc, "team_id", "") or ""),
                }

        def _resolve_team(uid: str):
            m = user_map.get(uid, {})
            tid = _attendance_team_id(uid, m.get("teamId", ""))
            return tid, _team_name_static(tid), m.get("name", uid)

        # ── 组装统一行 ──
        results: List[Dict[str, Any]] = []

        def _project_type_label(pc1: Any) -> str:
            """将 project_category_1 值映射为项目类型标签。"""
            s = str(pc1 or "").strip()
            if s and s != "None":
                return s
            return "其他"

        # B 表 → 软件开发
        for uid, wdc, need_stat, pc1, tid, content, _scenario, vt, pn3 in b_rows:
            uid = str(uid or "").strip()
            if not uid:
                continue
            # 仅统计 need_statistic = "是" 的条目
            ns = str(need_stat or "").strip()
            if ns != "是":
                continue
            # 排除工作日耗时为 0 或无数据的条目
            if wdc is None or not (wdc == wdc and float(wdc) > 0):
                continue
            team_id, team_name, user_name = _resolve_team(uid)
            results.append({
                "userId": uid,
                "userName": user_name,
                "teamId": team_id,
                "teamName": team_name,
                "taskType": "软件开发",
                "projectType": _project_type_label(pc1),
                "taskId": str(tid or ""),
                "content": str(content or ""),
                "workdayCosthour": float(wdc) if wdc is not None and wdc == wdc else 0.0,
                "vehicleType2": str(vt or "").strip() if vt else "",
                "projectName3": str(pn3 or "").strip() if pn3 else "",
            })

        # C 表 → 软件开发（B/C 去重：以 task_id 为 key，B 表优先）
        b_task_ids = {
            r["taskId"]
            for r in results
            if r.get("taskId")
        }
        for uid, wdc, need_stat, pc1, tid, content, _scenario, vt, pn3 in c_rows:
            uid = str(uid or "").strip()
            if not uid:
                continue
            # 仅统计 need_statistic = "是" 的条目
            ns = str(need_stat or "").strip()
            if ns != "是":
                continue
            # 排除工作日耗时为 0 或无数据的条目
            if wdc is None or not (wdc == wdc and float(wdc) > 0):
                continue
            task_id_str = str(tid or "")
            if task_id_str in b_task_ids:
                continue  # B 表已有，跳过
            team_id, team_name, user_name = _resolve_team(uid)
            results.append({
                "userId": uid,
                "userName": user_name,
                "teamId": team_id,
                "teamName": team_name,
                "taskType": "软件开发",
                "projectType": _project_type_label(pc1),
                "taskId": task_id_str,
                "content": str(content or ""),
                "workdayCosthour": float(wdc) if wdc is not None and wdc == wdc else 0.0,
                "vehicleType2": str(vt or "").strip() if vt else "",
                "projectName3": str(pn3 or "").strip() if pn3 else "",
            })

        # 问题处理
        for uid, wdc, need_stat, pc1, vt, pn3, tid, content in issue_rows:
            uid = str(uid or "").strip()
            if not uid:
                continue
            # 仅统计 need_statistic = "是" 的条目
            ns = str(need_stat or "").strip()
            if ns != "是":
                continue
            # 排除工作日耗时为 0 或无数据的条目
            if wdc is None or not (wdc == wdc and float(wdc) > 0):
                continue
            team_id, team_name, user_name = _resolve_team(uid)
            results.append({
                "userId": uid,
                "userName": user_name,
                "teamId": team_id,
                "teamName": team_name,
                "taskType": "问题处理",
                "projectType": _project_type_label(pc1),
                "taskId": str(tid or ""),
                "content": str(content or ""),
                "workdayCosthour": float(wdc) if wdc is not None and wdc == wdc else 0.0,
                "vehicleType2": str(vt or "").strip() if vt else "",
                "projectName3": str(pn3 or "").strip() if pn3 else "",
            })

        # ── 算法开发：algo_task_details ──
        for uid, wdc, need_stat, pc1, tid, content, _scenario, vt, pn3 in algo_task_rows:
            uid = str(uid or "").strip()
            if not uid:
                continue
            if str(need_stat or "").strip() != "是":
                continue
            if wdc is None or not (wdc == wdc and float(wdc) > 0):
                continue
            team_id, team_name, user_name = _resolve_team(uid)
            results.append({
                "userId": uid,
                "userName": user_name,
                "teamId": team_id,
                "teamName": team_name,
                "taskType": "软件开发",
                "projectType": _project_type_label(pc1),
                "taskId": str(tid or ""),
                "content": str(content or ""),
                "workdayCosthour": float(wdc) if wdc is not None and wdc == wdc else 0.0,
                "vehicleType2": str(vt or "").strip() if vt else "",
                "projectName3": str(pn3 or "").strip() if pn3 else "",
            })

        # ── 算法问题：algo_issue_details ──
        for uid, wdc, need_stat, pc1, vt, pn3, tid, content in algo_issue_rows:
            uid = str(uid or "").strip()
            if not uid:
                continue
            if str(need_stat or "").strip() != "是":
                continue
            if wdc is None or not (wdc == wdc and float(wdc) > 0):
                continue
            team_id, team_name, user_name = _resolve_team(uid)
            results.append({
                "userId": uid,
                "userName": user_name,
                "teamId": team_id,
                "teamName": team_name,
                "taskType": "问题处理",
                "projectType": _project_type_label(pc1),
                "taskId": str(tid or ""),
                "content": str(content or ""),
                "workdayCosthour": float(wdc) if wdc is not None and wdc == wdc else 0.0,
                "vehicleType2": str(vt or "").strip() if vt else "",
                "projectName3": str(pn3 or "").strip() if pn3 else "",
            })

        # ── 白名单过滤：只保留指定参与人员 ──
        results = [r for r in results if r["userId"] in ATTENDANCE_PARTICIPANT_USER_IDS]

        return results
    finally:
        algo_session.close()
        session.close()


def _aggregate_by_project_type(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """按项目类型聚合：{ "研发项目": {hours, count}, ... }"""
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        label = r.get("projectType", "其他")
        if label == "其他":
            continue  # 跳过未分类
        bucket = agg.setdefault(label, {"hours": 0.0, "count": 0})
        bucket["hours"] += r.get("workdayCosthour", 0.0)
        bucket["count"] += 1
    for v in agg.values():
        v["hours"] = round(v["hours"], 2)
    return agg


def _aggregate_by_task_type(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """按任务类型聚合：{ "软件开发": {hours, count}, "问题处理": {hours, count} }"""
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        tt = r.get("taskType", "未知")
        bucket = agg.setdefault(tt, {"hours": 0.0, "count": 0})
        bucket["hours"] += r.get("workdayCosthour", 0.0)
        bucket["count"] += 1
    for v in agg.values():
        v["hours"] = round(v["hours"], 2)
    return agg


def _aggregate_by_vehicle_type(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """按车型聚合：{ "通用": {hours, count}, ... }"""
    agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        vt = (r.get("vehicleType2") or "").strip()
        if not vt:
            continue
        bucket = agg.setdefault(vt, {"hours": 0.0, "count": 0})
        bucket["hours"] += r.get("workdayCosthour", 0.0)
        bucket["count"] += 1
    for v in agg.values():
        v["hours"] = round(v["hours"], 2)
    # 过滤掉 hours 为 0 的条目
    return {k: v for k, v in agg.items() if v["hours"] > 0}


def _aggregate_vehicle_by_source(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """按车型 × 来源(B/C/Issue) 聚合任务数：{ "通用": { "B": 635, "C": 10, "Issue": 296, "total": 941 } }"""
    agg: Dict[str, Dict[str, int]] = {}
    for r in rows:
        vt = (r.get("vehicleType2") or "").strip()
        if not vt:
            continue
        src = r.get("source", "?")
        bucket = agg.setdefault(vt, {"B": 0, "C": 0, "Issue": 0, "total": 0})
        bucket[src] = bucket.get(src, 0) + 1
        bucket["total"] += 1
    return agg


def _total_hours_and_count(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    total_h = round(sum(r.get("workdayCosthour", 0.0) for r in rows), 2)
    total_c = len(rows)
    return {"hours": total_h, "taskCount": total_c}


# ── 接口 1：所有组别各自的数据汇总 ──

def workday_costhour_team_summary_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """各小组明细数据汇总，返回按 team 分组的 byProjectType / byTaskType / byVehicleType。"""
    start_dt, end_dt, err = _resolve_time_range(payload)
    if err:
        return {"success": False, "error": err, "data": {}}

    rows = _query_workday_costhour_base(start_dt, end_dt)
    all_total = _total_hours_and_count(rows)

    team_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        tid = r.get("teamId", "")
        team_buckets.setdefault(tid, []).append(r)

    teams = []
    for tid in sorted(team_buckets.keys()):
        team_rows = team_buckets[tid]
        tname = team_rows[0].get("teamName", _team_name_static(tid)) if team_rows else _team_name_static(tid)
        tt = _total_hours_and_count(team_rows)
        teams.append({
            "teamId": tid,
            "teamName": tname,
            "totalHours": tt["hours"],
            "totalCount": tt["taskCount"],
            "byProjectType": _aggregate_by_project_type(team_rows),
            "byVehicleType": _aggregate_by_vehicle_type(team_rows),
            "byVehicleSource": _aggregate_vehicle_by_source(team_rows),
            "byTaskType": _aggregate_by_task_type(team_rows),
        })

    return {
        "success": True,
        "data": {
            "timeRange": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
            "total": all_total,
            "teams": teams,
        },
    }


# ── 接口 2：部门级项目类型和车型统计 ──

def workday_costhour_department_aggregate_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """部门级聚合：byProjectType / byVehicleType（全部门，不做团队拆分）。"""
    start_dt, end_dt, err = _resolve_time_range(payload)
    if err:
        return {"success": False, "error": err, "data": {}}

    rows = _query_workday_costhour_base(start_dt, end_dt)
    all_total = _total_hours_and_count(rows)

    return {
        "success": True,
        "data": {
            "timeRange": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
            "total": all_total,
            "byProjectType": _aggregate_by_project_type(rows),
            "byVehicleType": _aggregate_by_vehicle_type(rows),
        },
    }


# ── 接口 3：任务状态明细 ──

def workday_costhour_task_status_detail_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """按项目类型展开 → 软件开发/问题处理 的层级结构（全局数据）。"""
    start_dt, end_dt, err = _resolve_time_range(payload)
    if err:
        return {"success": False, "error": err, "data": {}}

    rows = _query_workday_costhour_base(start_dt, end_dt)

    all_total = _total_hours_and_count(rows)

    group_buckets: Dict[str, Dict[str, Dict[str, float]]] = {}
    for r in rows:
        pt_label = r.get("projectType", "其他")
        if pt_label == "其他":
            continue
        tt = r.get("taskType", "未知")
        bucket = group_buckets.setdefault(pt_label, {}).setdefault(tt, {"hours": 0.0, "count": 0})
        bucket["hours"] += r.get("workdayCosthour", 0.0)
        bucket["count"] += 1

    project_type_order = ["研发项目", "产品项目", "订单项目"]
    details = []
    summary_sw = {"hours": 0.0, "count": 0}
    summary_issue = {"hours": 0.0, "count": 0}

    for pt in project_type_order:
        children_map = group_buckets.get(pt, {})
        children = []
        for tt in ["软件开发", "问题处理"]:
            v = children_map.get(tt, {"hours": 0.0, "count": 0})
            child = {"taskType": tt, "hours": round(v["hours"], 2), "count": int(v["count"])}
            children.append(child)
            if tt == "软件开发":
                summary_sw["hours"] += v["hours"]
                summary_sw["count"] += int(v["count"])
            else:
                summary_issue["hours"] += v["hours"]
                summary_issue["count"] += int(v["count"])

        pt_total_h = round(sum(c["hours"] for c in children), 2)
        pt_total_c = sum(c["count"] for c in children)
        details.append({
            "projectType": pt,
            "totalHours": pt_total_h,
            "totalCount": pt_total_c,
            "children": children,
        })

    summary_sw["hours"] = round(summary_sw["hours"], 2)
    summary_issue["hours"] = round(summary_issue["hours"], 2)

    return {
        "success": True,
        "data": {
            "timeRange": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
            "total": all_total,
            "details": details,
            "summary": {
                "软件开发": summary_sw,
                "问题处理": summary_issue,
                "totalHours": all_total["hours"],
                "totalCount": all_total["taskCount"],
            },
        },
    }


def workday_costhour_member_summary_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """个人维度工作日耗时汇总：三张明细表统一查询后按 userId 聚合。"""
    start_dt, end_dt, err = _resolve_time_range(payload)
    if err:
        return {"success": False, "error": err, "data": {}}

    team_id_filter = str(payload.get("team_id", "") or "").strip()

    rows = _query_workday_costhour_base(start_dt, end_dt)
    if team_id_filter:
        rows = [r for r in rows if str(r.get("teamId", "") or "").strip() == team_id_filter]

    # 出勤表人员名单是固定参与人员 roster，不能因某季度没有任务数据而缩减。
    # 先从 user_character 补齐所有人员，再把本季度工时聚合到对应人员。
    member_map: Dict[str, Dict[str, Any]] = {}
    roster_session = SessionLocal()
    try:
        roster_rows = (
            roster_session.query(DbUserCharacter)
            .filter(DbUserCharacter.user_id.in_(list(ATTENDANCE_PARTICIPANT_USER_IDS)))
            .all()
        )
        roster_by_id = {
            str(getattr(item, "user_id", "") or "").strip(): item
            for item in roster_rows
        }
    finally:
        roster_session.close()

    for uid in sorted(ATTENDANCE_PARTICIPANT_USER_IDS):
        profile = roster_by_id.get(uid)
        actual_team_id = str(getattr(profile, "team_id", "") or "") if profile else ""
        team_id = _attendance_team_id(uid, actual_team_id)
        team_name = _team_name_static(team_id)
        user_name = str(getattr(profile, "name", "") or uid) if profile else uid
        if team_id_filter and team_id != team_id_filter:
            continue
        member_map[uid] = {
            "userId": uid,
            "userName": user_name,
            "teamId": team_id,
            "teamName": team_name,
            "workdayCosthour": 0.0,
            "taskCount": 0,
        }

    for r in rows:
        uid = str(r.get("userId", "") or "").strip()
        if not uid:
            continue
        if uid not in ATTENDANCE_PARTICIPANT_USER_IDS:
            continue
        if team_id_filter and str(r.get("teamId", "") or "").strip() != team_id_filter:
            continue
        bucket = member_map.setdefault(uid, {
            "userId": uid,
            "userName": r.get("userName", uid),
            "teamId": str(r.get("teamId", "") or ""),
            "teamName": r.get("teamName") or _team_name_static(r.get("teamId")),
            "workdayCosthour": 0.0,
            "taskCount": 0,
        })
        bucket["workdayCosthour"] += float(r.get("workdayCosthour") or 0.0)
        bucket["taskCount"] += 1

    members = []
    for item in member_map.values():
        item["workdayCosthour"] = round(float(item.get("workdayCosthour") or 0.0), 2)
        members.append(item)
    members.sort(key=lambda x: (str(x.get("teamId", "")), str(x.get("userName", ""))))

    teams_seen: Dict[str, str] = {}
    for m in members:
        tid = str(m.get("teamId", "") or "")
        teams_seen[tid] = m.get("teamName") or _team_name_static(tid)
    teams = [
        {"teamId": tid, "teamName": teams_seen[tid]}
        for tid in sorted(teams_seen.keys())
    ]

    return {
        "success": True,
        "data": {
            "timeRange": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
            "teamId": team_id_filter,
            "teamName": _team_name_static(team_id_filter) if team_id_filter else "全部",
            "teams": teams,
            "members": members,
            "total": _total_hours_and_count(rows),
        },
    }


# ── 接口 4：指定小组 + 项目类型的明细列表 ──

def workday_costhour_team_project_detail_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    按 teamId + projectType 过滤，返回每条任务的明细列表。

    参数:
      - start_time / end_time (必填)
      - team_id (必填): "0"=导航组, "1"=对接组
      - project_type (必填): 如 "产品项目"、"研发项目"、"订单项目"
    """
    start_dt, end_dt, err = _resolve_time_range(payload)
    if err:
        return {"success": False, "error": err, "data": {}}

    team_id = str(payload.get("team_id", "")).strip()
    project_type = str(payload.get("project_type", "")).strip()

    if not team_id:
        return {"success": False, "error": "team_id is required", "data": {}}
    if not project_type:
        return {"success": False, "error": "project_type is required", "data": {}}

    rows = _query_workday_costhour_base(start_dt, end_dt)

    # 按 teamId + projectType 过滤
    filtered = [
        r for r in rows
        if r.get("teamId") == team_id and r.get("projectType") == project_type
    ]

    # 组装明细列表
    items = []
    for r in filtered:
        items.append({
            "taskId": r.get("taskId", ""),
            "content": r.get("content", ""),
            "userName": r.get("userName", ""),
            "taskType": r.get("taskType", ""),
            "vehicleType": r.get("vehicleType2", ""),
            "workdayCosthour": r.get("workdayCosthour", 0.0),
        })

    # 按工时降序排列
    items.sort(key=lambda x: x["workdayCosthour"], reverse=True)

    total = _total_hours_and_count(filtered)

    return {
        "success": True,
        "data": {
            "timeRange": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
            "teamId": team_id,
            "teamName": _team_name_static(team_id),
            "projectType": project_type,
            "total": total,
            "items": items,
        },
    }


# ── 接口 5：项目名称明细（按 project_name_3 展开） ──

def workday_costhour_project_name_detail_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """按项目类型 → project_name_3 → 软件开发/问题处理 的层级结构。"""
    start_dt, end_dt, err = _resolve_time_range(payload)
    if err:
        return {"success": False, "error": err, "data": {}}

    rows = _query_workday_costhour_base(start_dt, end_dt)
    all_total = _total_hours_and_count(rows)

    # 三层嵌套: projectType → projectName3 → taskType → {hours, count}
    project_buckets: Dict[str, Dict[str, Dict[str, Dict[str, float]]]] = {}
    for r in rows:
        pt = r.get("projectType", "其他")
        pn3 = r.get("projectName3") or "未分类"
        tt = r.get("taskType", "未知")
        bucket = (
            project_buckets.setdefault(pt, {})
            .setdefault(pn3, {})
            .setdefault(tt, {"hours": 0.0, "count": 0})
        )
        bucket["hours"] += r.get("workdayCosthour", 0.0)
        bucket["count"] += 1

    project_type_order = ["研发项目", "产品项目", "订单项目"]
    details = []
    for pt in project_type_order:
        pn3_map = project_buckets.get(pt, {})
        pn3_items = []
        for pn3 in sorted(pn3_map.keys()):
            tt_map = pn3_map[pn3]
            children = []
            for tt in ["软件开发", "问题处理"]:
                v = tt_map.get(tt, {"hours": 0.0, "count": 0})
                children.append({
                    "taskType": tt,
                    "hours": round(v["hours"], 2),
                    "count": int(v["count"]),
                })
            pn3_total_h = round(sum(c["hours"] for c in children), 2)
            pn3_total_c = sum(c["count"] for c in children)
            pn3_items.append({
                "projectName": pn3,
                "totalHours": pn3_total_h,
                "totalCount": pn3_total_c,
                "children": children,
            })
        pt_total_h = round(sum(item["totalHours"] for item in pn3_items), 2)
        pt_total_c = sum(item["totalCount"] for item in pn3_items)
        details.append({
            "projectType": pt,
            "totalHours": pt_total_h,
            "totalCount": pt_total_c,
            "projectNames": pn3_items,
        })

    return {
        "success": True,
        "data": {
            "timeRange": {
                "start_time": start_dt.isoformat(),
                "end_time": end_dt.isoformat(),
            },
            "total": all_total,
            "details": details,
        },
    }
