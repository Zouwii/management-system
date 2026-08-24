"""应用组问题分析报表。

这是独立于 workday_costhour 的业务查询：数据来源是
``program_issue_detail``，按问题类型、原因、提示、优先级和项目维度
组织成前端报表需要的结构，不复用有效工时聚合口径。
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from base.db.engine import OnsiteSessionLocal, SessionLocal
from base.db.orm import OnsiteProblemDetail, ProgramIssueDetail, UserCharacter


TYPE_ORDER = [
    "本体导航/导航",
    "本体导航/定位",
    "本体导航/建图",
    "本体导航/非本体导航",
    "TB单异常/资料不全",
    "未填写",
]
CAUSE_TYPE_ORDER = ["本体导航/导航", "本体导航/定位", "本体导航/建图"]
PROMPT_TYPE_ORDER = ["本体导航/导航", "本体导航/定位"]
PRIORITY_ORDER = ["非常紧急", "紧急", "普通"]
# 历史数据中部分应用工程师仍保留在导航组 team_id=0；在人员表完成迁移前，
# 用这份兼容名单保证应用组报表不会把他们漏掉。
APPLICATION_TEAM_USER_IDS = {
    "2108411066921750",  # 潘铮
    "265352386036276420",  # 郑世玉
    "495200335237410081",  # 钟昌郎
    "312542394537803309",  # 陈文斌
}


def _quarter_range(year: Any, quarter: Any) -> Tuple[datetime, datetime]:
    year_int = int(year)
    quarter_int = int(str(quarter).upper().replace("Q", ""))
    if quarter_int not in {1, 2, 3, 4}:
        raise ValueError("quarter must be Q1, Q2, Q3 or Q4")
    start_month = (quarter_int - 1) * 3 + 1
    start = datetime(year_int, start_month, 1)
    end = datetime(year_int + 1, 1, 1) if quarter_int == 4 else datetime(year_int, start_month + 3, 1)
    return start, end


def _text(value: Any) -> str:
    value = str(value or "").strip()
    return value or "未填写"


def _path(*values: Any) -> str:
    parts = [_text(value) for value in values if str(value or "").strip()]
    return " / ".join(parts) if parts else "未填写"


def _type_label(first: Any, second: Any) -> str:
    first_text = _text(first)
    second_text = _text(second)
    if first_text.startswith("TB单异常") or second_text == "资料不全":
        return "TB单异常/资料不全"
    if first_text == "本体导航":
        return f"本体导航/{second_text}" if second_text != "未填写" else "本体导航/导航"
    if first_text in {"定位", "建图", "非本体导航"}:
        return f"本体导航/{first_text}"
    if first_text == "未填写":
        return "未填写"
    return f"本体导航/{first_text}"


def _priority_label(value: Any) -> str:
    """将 Teambition priority 兼容映射到报表的三级优先级。"""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "普通"
    if number >= 3:
        return "非常紧急"
    if number == 2:
        return "紧急"
    return "普通"


def _pct(count: int, denominator: int) -> float:
    return round(count * 100 / denominator, 2) if denominator else 0.0


def _rows(counter: Counter, denominator: int) -> List[Dict[str, Any]]:
    result = [
        {"label": label, "count": count, "ratio": _pct(count, denominator)}
        for label, count in counter.most_common()
    ]
    result.append({"label": "合计", "count": denominator, "ratio": 100.0 if denominator else 0.0})
    return result


def _record_from_row(row: ProgramIssueDetail) -> Dict[str, Any]:
    type_label = _type_label(row.problem_type_1, row.problem_type_2)
    project = _path(row.project_catagory_1, row.project_catagory_2, row.project_catagory_3)
    return {
        "id": row.id,
        "taskId": _text(row.task_id),
        "date": row.created_at_ding.isoformat() if row.created_at_ding else "",
        "description": _text(row.content),
        "typeLabel": type_label,
        "causePath": _path(row.cause_level_1, row.cause_level_2, row.cause_level_3),
        "causeLevel1": _text(row.cause_level_1),
        "causeLevel2": _text(row.cause_level_2),
        "causeLevel3": _text(row.cause_level_3),
        "promptPath": _path(row.problem_note_info_1, row.problem_note_info_2, row.problem_note_info_3),
        "projectPath": project,
        "vehiclePath": _path(row.vehicle_1, row.vehicle_2),
        "softwareVersion": _text(row.software_version),
        "priority": _priority_label(row.priority),
        "priorityRaw": row.priority,
        "problemTypeRaw": {"level1": _text(row.problem_type_1), "level2": _text(row.problem_type_2)},
        "onsiteLinked": False,
    }


def _application_members(session) -> List[Dict[str, str]]:
    """返回应用组人员选项；人员身份来自 user_character，不在接口中写死姓名。"""
    rows = (
        session.query(UserCharacter.user_id, UserCharacter.name)
        .filter(UserCharacter.team_id == "3")
        .order_by(UserCharacter.name.asc(), UserCharacter.user_id.asc())
        .all()
    )
    members = {str(user_id): {"userId": str(user_id), "name": _text(name)} for user_id, name in rows if user_id}
    legacy_rows = (
        session.query(UserCharacter.user_id, UserCharacter.name)
        .filter(UserCharacter.user_id.in_(APPLICATION_TEAM_USER_IDS))
        .all()
    )
    for user_id, name in legacy_rows:
        members.setdefault(str(user_id), {"userId": str(user_id), "name": _text(name)})
    # 历史数据兼容人员没有迁移 team_id 时，仍从问题表中发现其身份；姓名优先从人员表取。
    for user_id in APPLICATION_TEAM_USER_IDS:
        members.setdefault(user_id, {"userId": user_id, "name": user_id})
    return list(members.values())


def _distinct_sql_values(rows: Iterable[ProgramIssueDetail], *fields: str) -> Dict[str, List[str]]:
    """从当前 SQL 结果行生成维度枚举，保证页面选项与数据库实际值一致。"""
    values = {field: set() for field in fields}
    for row in rows:
        for field in fields:
            value = str(getattr(row, field, "") or "").strip()
            if value:
                values[field].add(value)
    return {field: sorted(items) for field, items in values.items()}


def application_team_options_service() -> Dict[str, Any]:
    """查询应用组报表的筛选项及 SQL 维度值。"""
    session = SessionLocal()
    try:
        members = _application_members(session)
        member_ids = [item["userId"] for item in members]
        rows = (
            session.query(ProgramIssueDetail)
            .filter(ProgramIssueDetail.executor_id.in_(member_ids))
            .all()
            if member_ids else []
        )
        years = sorted({row.created_at_ding.year for row in rows if row.created_at_ding}, reverse=True)
        quarters = sorted({(row.created_at_ding.month - 1) // 3 + 1 for row in rows if row.created_at_ding})
        dimensions = _distinct_sql_values(
            rows,
            "problem_type_1", "problem_type_2",
            "cause_level_1", "cause_level_2", "cause_level_3",
            "problem_note_info_1", "problem_note_info_2", "problem_note_info_3",
            "project_catagory_1", "project_catagory_2", "project_catagory_3",
            "priority", "software_version",
        )
        return {
            "success": True,
            "data": {
                "members": members,
                "years": years,
                "quarters": quarters,
                "dimensions": dimensions,
            },
        }
    finally:
        session.close()


def _cause_section(records: Iterable[Dict[str, Any]], type_label: str) -> Dict[str, Any]:
    scoped = [record for record in records if record["typeLabel"] == type_label]
    denominator = len(scoped)
    cause_counter = Counter(record["causeLevel1"] for record in scoped)
    detail_counter: Dict[str, Counter] = defaultdict(Counter)
    for record in scoped:
        detail_counter[record["causeLevel1"]][
            _path(record["causeLevel2"], record["causeLevel3"])
        ] += 1
    details = {
        cause: _rows(counter, sum(counter.values()))
        for cause, counter in detail_counter.items()
    }
    return {
        "type": type_label,
        "total": denominator,
        "rows": _rows(cause_counter, denominator),
        "secondary": details,
    }


def _matrix(records: List[Dict[str, Any]], row_key: str, columns: List[str]) -> Dict[str, Any]:
    row_labels = sorted({str(record.get(row_key) or "未填写") for record in records})
    counts = Counter((record.get(row_key) or "未填写", record["typeLabel"]) for record in records)
    return {
        "columns": columns,
        "rows": [
            {"label": label, "values": {column: counts[(label, column)] for column in columns}}
            for label in row_labels
        ],
    }


def _result_table_definitions() -> List[Dict[str, Any]]:
    """页面最终结果表契约：10 张统计表 + 1 张现场关联明细表。"""
    return [
        {"key": "typeStats", "title": "问题类型统计", "kind": "stat"},
        {"key": "causeStats.navigation", "title": "导航问题原因统计", "kind": "stat"},
        {"key": "causeStats.localization", "title": "定位问题原因统计", "kind": "stat"},
        {"key": "causeStats.mapping", "title": "建图问题原因统计", "kind": "stat"},
        {"key": "promptStats.navigation", "title": "导航问题提示信息统计", "kind": "stat"},
        {"key": "promptStats.localization", "title": "定位问题提示信息统计", "kind": "stat"},
        {"key": "handlingStats", "title": "问题处理方式及耗时", "kind": "stat"},
        {"key": "priorityMatrix", "title": "优先级矩阵", "kind": "matrix"},
        {"key": "documentValueMatrix", "title": "排查文档价值矩阵", "kind": "matrix"},
        {"key": "projectMatrix", "title": "项目 × 问题类型矩阵", "kind": "matrix"},
        {"key": "onsiteLinks", "title": "关联现场单子", "kind": "detail"},
    ]


def application_team_report_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload or {}
    try:
        start, end = _quarter_range(payload.get("year", datetime.now().year), payload.get("quarter", "Q1"))
    except (TypeError, ValueError) as exc:
        return {"success": False, "error": str(exc), "data": {}}

    session = SessionLocal()
    onsite_session = OnsiteSessionLocal()
    try:
        members = _application_members(session)
        application_ids = [item["userId"] for item in members]
        executor_id = str(payload.get("executorId") or payload.get("userId") or "").strip()
        if executor_id:
            if executor_id not in set(application_ids):
                return {"success": False, "error": "executorId is not an application-team member", "data": {}}
            application_ids = [executor_id]
        if not application_ids:
            return {"success": True, "data": _empty_report(start, end)}

        rows = (
            session.query(ProgramIssueDetail)
            # 问题类型统计的固定口径：只使用 program_issue_detail，
            # 按 executor_id 识别用户、按 created_at_ding 识别季度；不使用 need_statistic。
            .filter(ProgramIssueDetail.executor_id.in_(application_ids))
            .filter(ProgramIssueDetail.created_at_ding >= start)
            .filter(ProgramIssueDetail.created_at_ding < end)
            .order_by(ProgramIssueDetail.created_at_ding.asc(), ProgramIssueDetail.id.asc())
            .all()
        )
        records = [_record_from_row(row) for row in rows]

        task_ids = [record["taskId"] for record in records]
        onsite_rows = (
            onsite_session.query(OnsiteProblemDetail)
            .filter(OnsiteProblemDetail.task_id.in_(task_ids))
            .all()
            if task_ids else []
        )
        onsite_ids = {str(row.task_id) for row in onsite_rows}
        for record in records:
            record["onsiteLinked"] = record["taskId"] in onsite_ids

        total = len(records)
        type_counter = Counter(record["typeLabel"] for record in records)
        prompt_sections = []
        for type_label in PROMPT_TYPE_ORDER:
            scoped = [record for record in records if record["typeLabel"] == type_label]
            prompt_sections.append({
                "type": type_label,
                "total": len(scoped),
                "rows": _rows(Counter(record["promptPath"] for record in scoped), len(scoped)),
            })

        type_columns = [label for label in TYPE_ORDER[:4] if label in type_counter]
        type_columns += sorted(label for label in type_counter if label not in type_columns)
        priority_matrix = _matrix(records, "priority", type_columns)
        project_matrix = _matrix(records, "projectPath", type_columns)
        linked = [record for record in records if record["onsiteLinked"]]
        type_by_task = {record["taskId"]: record["typeLabel"] for record in records}
        doc_records = [
            {"typeLabel": type_by_task.get(str(row.task_id), "未填写"), "docValue": _text(row.doc_value)}
            for row in onsite_rows if row.doc_value and str(row.task_id) in type_by_task
        ]
        document_value_matrix = _matrix(doc_records, "docValue", type_columns)
        dimensions = _distinct_sql_values(
            rows,
            "problem_type_1", "problem_type_2",
            "cause_level_1", "cause_level_2", "cause_level_3",
            "problem_note_info_1", "problem_note_info_2", "problem_note_info_3",
            "project_catagory_1", "project_catagory_2", "project_catagory_3",
            "priority", "software_version",
        )
        return {"success": True, "data": {
            "period": {"start": start.isoformat(), "end": end.isoformat()},
            "scope": {"team": "application", "executorId": executor_id or None},
            "filters": {"year": int(payload.get("year", start.year)), "quarter": f"Q{(start.month - 1) // 3 + 1}", "executorId": executor_id or None},
            "members": members,
            "total": total,
            "typeStats": {"rows": _rows(type_counter, total), "order": type_columns},
            "causeStats": [_cause_section(records, type_label) for type_label in CAUSE_TYPE_ORDER],
            "promptStats": prompt_sections,
            "handlingStats": {"configured": False, "rows": []},
            "priorityMatrix": priority_matrix,
            "documentValueMatrix": {"configured": bool(doc_records), **document_value_matrix},
            "projectMatrix": project_matrix,
            "onsiteLinks": {"count": len(linked), "taskIds": [record["taskId"] for record in linked]},
            "dimensions": dimensions,
            "resultTableCount": len(_result_table_definitions()),
            "resultTables": _result_table_definitions(),
            "details": records,
        }}
    finally:
        onsite_session.close()
        session.close()


def _empty_report(start: datetime, end: datetime) -> Dict[str, Any]:
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "scope": {"team": "application", "executorId": None},
        "filters": {"year": start.year, "quarter": f"Q{(start.month - 1) // 3 + 1}", "executorId": None},
        "members": [],
        "total": 0,
        "typeStats": {"rows": _rows(Counter(), 0), "order": TYPE_ORDER},
        "causeStats": [], "promptStats": [],
        "handlingStats": {"configured": False, "rows": []},
        "priorityMatrix": {"columns": TYPE_ORDER[:4], "rows": []},
        "documentValueMatrix": {"configured": False, "columns": [], "rows": []},
        "projectMatrix": {"columns": TYPE_ORDER[:4], "rows": []},
        "onsiteLinks": {"count": 0, "taskIds": []}, "details": [],
        "dimensions": {},
        "resultTableCount": len(_result_table_definitions()),
        "resultTables": _result_table_definitions(),
    }
