from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select

from base.db.engine import PerfSessionLocal, SessionLocal
from base.db.orm import NavPerfQuarterResult, ServoPerfQuarterResult, UserCharacter
from base.organization.constants import stable_team_code
from base.organization.service import list_scope_members, list_scope_teams


def _to_decimal_3(x: Any) -> Decimal:
    """把入参转成 Decimal，并固定到 3 位小数（HALF_UP）。"""
    if x is None:
        return Decimal("0.000")
    d = Decimal(str(x))
    return d.quantize(Decimal("0.000"), rounding=ROUND_HALF_UP)


def _round3(x: Any) -> Decimal:
    return _to_decimal_3(x)


def _prev_year_quarter(year: int, quarter: int) -> Tuple[int, int]:
    if quarter <= 1:
        return year - 1, 4
    return year, quarter - 1


def _member_overall_score(work_hour_score: float, supervisor_score: float) -> Decimal:
    hour = Decimal(str(work_hour_score or 0))
    sup = Decimal(str(supervisor_score or 0))
    raw = hour * Decimal("0.7") + sup * Decimal("0.3")
    return _round3(raw)


def _threshold_interval_by_overall(overall_score: Decimal) -> Tuple[Decimal, Decimal]:
    """
    根据 overall_score 确定当前档位下限 / 下一档上限。
    区间：
    [0, 0.8)   -> lower=0,   upper=0.8
    [0.8, 1)   -> lower=0.8, upper=1.0
    [1.0, 1.2) -> lower=1.0, upper=1.2
    [1.2, 1.5) -> lower=1.2, upper=1.5
    [1.5, 2.0) -> lower=1.5, upper=2.0
    [2.0, +inf)-> lower=2.0, upper=2.0
    """
    if overall_score < Decimal("0.8"):
        return Decimal("0.000"), Decimal("0.800")
    if overall_score < Decimal("1.0"):
        return Decimal("0.800"), Decimal("1.000")
    if overall_score < Decimal("1.2"):
        return Decimal("1.000"), Decimal("1.200")
    if overall_score < Decimal("1.5"):
        return Decimal("1.200"), Decimal("1.500")
    if overall_score < Decimal("2.0"):
        return Decimal("1.500"), Decimal("2.000")
    return Decimal("2.000"), Decimal("2.000")


def _map_company_score(final_score: Decimal) -> Decimal:
    mapping = {
        Decimal("0.000"): Decimal("2.500"),
        Decimal("0.500"): Decimal("3.000"),
        Decimal("0.800"): Decimal("3.250"),
        Decimal("1.000"): Decimal("3.500"),
        Decimal("1.200"): Decimal("3.750"),
        Decimal("1.500"): Decimal("4.500"),
        Decimal("2.000"): Decimal("5.000"),
    }
    return mapping.get(final_score, Decimal("0.000"))


def _select_model_by_team_code(user_id: str):
    """根据 roster 团队编码选择导航/对接绩效表。"""
    uc_sess = SessionLocal()
    try:
        c_row = uc_sess.query(UserCharacter).filter(UserCharacter.user_id == user_id).first()
        if not c_row:
            raise ValueError("missing user_character roster row for user")
        team_code = stable_team_code(getattr(c_row, "team_code", None))
    finally:
        uc_sess.close()

    if team_code == "NAV":
        return NavPerfQuarterResult
    if team_code == "INTEGRATION":
        return ServoPerfQuarterResult
    raise ValueError(f"unsupported team: {team_code or 'unknown'}")


def _get_is_team_lead(user_id: str) -> bool:
    """Read the stable roster role used for the performance snapshot."""
    uc_sess = SessionLocal()
    try:
        c_row = uc_sess.query(UserCharacter).filter(UserCharacter.user_id == user_id).first()
        if not c_row:
            return False
        role = str(getattr(c_row, "job_role_code", "") or "").strip().upper()
        return role in {"TEAM_LEAD", "SYSTEM_ADMIN"}
    finally:
        uc_sess.close()


def fill_member_input_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    导入：写入 work_hour_score / supervisor_score，
    同时查询上季度 new_carry_balance / carry_decay_value 写入本行 prev_*，
    快照 is_team_lead。
    calc_status → filled。
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    user_id = str(payload.get("user_id") or payload.get("userId") or payload.get("userid") or "").strip()
    if not user_id:
        return {"success": False, "error": "missing user_id", "data": {}}

    hour_score = payload.get("work_hour_score", payload.get("hour_score", payload.get("hourScore")))
    manager_score = payload.get("supervisor_score", payload.get("manager_score", payload.get("managerScore")))

    now = datetime.now(timezone.utc)
    session = PerfSessionLocal()
    try:
        Model = _select_model_by_team_code(user_id)

        # 0 + 空 → 删除已有记录
        if (hour_score == 0 and manager_score is None) or (hour_score is None and manager_score == 0):
            stmt = select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
            row = session.scalars(stmt).first()
            if row:
                session.delete(row)
                session.commit()
            return {"success": True, "data": {"deleted": True}}

        if hour_score is None or manager_score is None:
            return {"success": False, "error": "missing hour_score or manager_score", "data": {}}
        is_lead = _get_is_team_lead(user_id)

        # ── 上季度结余：优先用手动覆盖值，否则自动查询上季 new_carry ──
        need_auto = ("prev_carry_balance" not in payload or payload["prev_carry_balance"] is None)
        prev_row = None
        if need_auto:
            prev_year, prev_q = _prev_year_quarter(year, quarter)
            prev_stmt = select(Model).where(
                Model.year == prev_year, Model.quarter == prev_q, Model.user_id == user_id,
            )
            prev_row = session.scalars(prev_stmt).first()

        if "prev_carry_balance" in payload and payload["prev_carry_balance"] is not None:
            prev_carry = float(payload["prev_carry_balance"])
        else:
            prev_carry = float(_round3(prev_row.new_carry_balance if prev_row else 0.0))

        # prev_decay_value 恒为 prev_carry_balance * 0.25，无需手动输入
        prev_decay = float(_round3(Decimal(str(prev_carry)) * Decimal("0.25")))

        stmt = select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
        row = session.scalars(stmt).first()
        already_calculated = row is not None and row.calc_status == "calculated"
        if row:
            row.is_team_lead = is_lead
            row.rule_code = payload.get("rule_code", payload.get("ruleCode")) or row.rule_code
            row.work_hour_score = float(hour_score)
            row.supervisor_score = float(manager_score)
            row.prev_carry_balance = prev_carry
            row.prev_decay_value = prev_decay
            if not already_calculated:
                row.calc_status = "filled"
            row.updated_at = now
        else:
            row = Model(
                year=year,
                quarter=quarter,
                user_id=user_id,
                is_team_lead=is_lead,
                rule_code=payload.get("rule_code", payload.get("ruleCode")) or "default_rule_code",
                calc_status="filled",
                work_hour_score=float(hour_score),
                supervisor_score=float(manager_score),
                prev_carry_balance=prev_carry,
                prev_decay_value=prev_decay,
                created_at=now,
                updated_at=now,
            )
            session.add(row)

        session.commit()

        # 有输入 → 自动触发计算（含组长），已计算过的不重复算
        if not already_calculated and hour_score is not None and manager_score is not None:
            calc_result = calculate_member_quarter_performance_service({
                "year": year, "quarter": quarter, "user_id": user_id,
            })
            # calculate 共享 scoped_session，提交后 row 可能过期，重新查询
            row = session.scalars(
                select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
            ).first()
            return {
                "success": True,
                "data": {
                    "id": row.id if row else None,
                    "calc_status": "calculated" if calc_result.get("success") else "filled",
                    "calc_error": calc_result.get("error"),
                },
            }

        return {"success": True, "data": {"id": row.id, "calc_status": row.calc_status}}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def query_quarter_performance_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    查询绩效结果：year + quarter 必填，user_id / teamCode 可选。
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    user_id = str(payload.get("user_id") or payload.get("userId") or payload.get("userid") or "").strip()
    team_code = str(payload.get("teamCode") or "").strip().upper()
    if team_code and team_code not in _TEAM_KEY_BY_CODE:
        return {"success": False, "error": f"unknown teamCode: {team_code}", "data": {}}

    TEAM_MODEL_MAP = {
        "NAV": (NavPerfQuarterResult, "NAV", "导航组"),
        "INTEGRATION": (ServoPerfQuarterResult, "INTEGRATION", "对接组"),
    }
    models = [TEAM_MODEL_MAP[team_code]] if team_code in TEAM_MODEL_MAP else [
        (NavPerfQuarterResult, "NAV", "导航组"),
        (ServoPerfQuarterResult, "INTEGRATION", "对接组"),
    ]

    session = PerfSessionLocal()
    try:
        results = []
        for Model, result_team_code, team_label in models:
            stmt = select(Model).where(Model.year == year, Model.quarter == quarter)
            if user_id:
                stmt = stmt.where(Model.user_id == user_id)
            rows = session.scalars(stmt).all()
            for row in rows:
                d = _row_to_dict(row)
                d["teamCode"] = result_team_code
                d["teamName"] = team_label
                results.append(d)
        return {"success": True, "data": {"results": results, "count": len(results)}}
    except Exception as e:
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def _row_to_dict(row) -> Dict[str, Any]:
    """将 ORM 行转为前端需要的字典。"""
    return {
        "id": row.id,
        "year": row.year,
        "quarter": row.quarter,
        "userId": row.user_id,
        "isTeamLead": row.is_team_lead,
        "ruleCode": row.rule_code,
        "calcStatus": row.calc_status,
        # 输入
        "workHourScore": row.work_hour_score,
        "supervisorScore": row.supervisor_score,
        # 计算
        "overallScore": row.overall_score,
        "prevCarryBalance": row.prev_carry_balance,
        "prevDecayValue": row.prev_decay_value,
        "compensationValue": row.compensation_value,
        "overflowValue": row.overflow_value,
        "finalScore": row.final_score,
        "newCarryBalance": row.new_carry_balance,
        "carryDecayValue": row.carry_decay_value,
        "companyScore": row.company_score,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
    }


def calculate_member_quarter_performance_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    计算（成员规则）：只读本行数据，不跨行查询。
    prev_carry_balance / prev_decay_value 由 import 时已写入。
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    user_id = str(payload.get("user_id") or payload.get("userId") or payload.get("userid") or "").strip()
    if not user_id:
        return {"success": False, "error": "missing user_id", "data": {}}

    session = PerfSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        Model = _select_model_by_team_code(user_id)

        stmt = select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
        row = session.scalars(stmt).first()
        if not row:
            return {"success": False, "error": "perf_quarter_result not found (need import first)", "data": {}}

        if row.work_hour_score is None or row.supervisor_score is None:
            return {"success": False, "error": "missing input hour_score/manager_score", "data": {}}

        # 1. 重新查询上一季度 new_carry，而非读本行旧值
        prev_year, prev_q = _prev_year_quarter(year, quarter)
        prev_stmt = select(Model).where(
            Model.year == prev_year, Model.quarter == prev_q, Model.user_id == user_id,
        )
        prev_row = session.scalars(prev_stmt).first()
        prev_carry_balance = _round3(prev_row.new_carry_balance if prev_row else 0.0)
        prev_decay_value = _round3(prev_carry_balance * Decimal("0.25"))

        # 回写到本行，保持 prev_carry/prev_decay 与实际一致
        row.prev_carry_balance = float(prev_carry_balance)
        row.prev_decay_value = float(prev_decay_value)

        # 2. 总体绩效（组长用平方公式）
        if bool(row.is_team_lead):
            overall_score = _round3(
                Decimal(str(row.work_hour_score)) ** 2 * Decimal("0.6")
                + Decimal(str(row.supervisor_score)) * Decimal("0.4")
            )
        else:
            overall_score = _member_overall_score(row.work_hour_score, row.supervisor_score)

        # 3. 档位判断
        interval_lower, interval_upper = _threshold_interval_by_overall(overall_score)
        compensation_value = _round3(overall_score - interval_upper)
        overflow_value = _round3(overall_score - interval_lower)

        # 4. 最终绩效
        can_upgrade = (prev_carry_balance + compensation_value) >= Decimal("0")
        if can_upgrade:
            final_score = interval_upper
            raw = prev_carry_balance + compensation_value - prev_decay_value
            new_carry_balance = _round3(raw) if raw >= Decimal("0") else Decimal("0.000")
        else:
            final_score = interval_lower
            new_carry_balance = _round3(prev_carry_balance * Decimal("0.75") + overflow_value)

        # 5. 衰减与公司绩效
        carry_decay_value = _round3(new_carry_balance * Decimal("0.25"))
        company_score = _map_company_score(final_score)

        # 6. 回写（只写计算产出，prev_carry/prev_decay 已由 import 写入，不动）
        row.overall_score = float(overall_score)
        row.compensation_value = float(compensation_value)
        row.overflow_value = float(overflow_value)
        row.final_score = float(final_score)
        row.new_carry_balance = float(new_carry_balance)
        row.carry_decay_value = float(carry_decay_value)
        row.company_score = float(company_score)
        row.calc_status = "calculated"
        row.updated_at = now

        session.commit()
        return {
            "success": True,
            "data": {
                "overallScore": float(overall_score),
                "finalScore": float(final_score),
                "newCarryBalance": float(new_carry_balance),
                "carryDecayValue": float(carry_decay_value),
                "companyScore": float(company_score),
            },
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


_TEAM_CODE_BY_KEY = {"nav": "NAV", "servo": "INTEGRATION"}
_TEAM_KEY_BY_CODE = {value: key for key, value in _TEAM_CODE_BY_KEY.items()}


def list_team_import_users_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    查某组某季度的所有成员及其 import 状态。
    返回: [{userId, userName, workHourScore, supervisorScore, calcStatus,
             isTeamLead, prevCarryBalance, prevDecayValue}, ...]
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    team_code = str(payload.get("teamCode", "") or "").strip().upper()
    if team_code not in _TEAM_KEY_BY_CODE:
        return {"success": False, "error": f"unknown teamCode: {team_code}", "data": {}}

    Model = NavPerfQuarterResult if team_code == "NAV" else ServoPerfQuarterResult

    perf_sess = PerfSessionLocal()
    try:
        # 统一从季度绩效 Scope 解析人员，保留两张绩效表的存储模型。
        members = list_scope_members("QUARTER_PERFORMANCE", team_code)

        # ── 本季度绩效记录 ──
        perf_rows = perf_sess.query(Model).filter(
            Model.year == year, Model.quarter == quarter,
        ).all()
        perf_map = {r.user_id: r for r in perf_rows}

        # ── 上季度绩效记录（用于预填 prev_carry / prev_decay）──
        prev_year, prev_q = _prev_year_quarter(year, quarter)
        prev_rows = perf_sess.query(Model).filter(
            Model.year == prev_year, Model.quarter == prev_q,
        ).all()
        prev_map = {r.user_id: r for r in prev_rows}

        result = []
        for u in members:
            uid = u.get("userId")
            pr = perf_map.get(uid)
            pv = prev_map.get(uid)

            # 优先用本行已存值，否则取上季计算的 new_carry
            if pr and pr.prev_carry_balance != 0:
                prev_carry = float(_round3(pr.prev_carry_balance))
            elif pv:
                prev_carry = float(_round3(pv.new_carry_balance))
            else:
                prev_carry = 0.0

            # prev_decay 恒为 prev_carry * 0.25，无需存多份
            prev_decay = float(_round3(Decimal(str(prev_carry)) * Decimal("0.25")))

            result.append({
                "userId": uid,
                "userName": u.get("userName") or uid,
                "isTeamLead": bool(u.get("isTeamLead")),
                "workHourScore": pr.work_hour_score if pr else None,
                "supervisorScore": pr.supervisor_score if pr else None,
                "calcStatus": pr.calc_status if pr else None,
                "prevCarryBalance": prev_carry,
                "prevDecayValue": prev_decay,
                # 已计算字段（有则返回）
                "overallScore": pr.overall_score if pr else None,
                "compensationValue": pr.compensation_value if pr else None,
                "overflowValue": pr.overflow_value if pr else None,
                "finalScore": pr.final_score if pr else None,
                "newCarryBalance": pr.new_carry_balance if pr else None,
                "carryDecayValue": pr.carry_decay_value if pr else None,
                "companyScore": pr.company_score if pr else None,
            })
        return {"success": True, "data": {"members": result, "count": len(result)}}
    finally:
        perf_sess.close()


def batch_import_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    批量导入：接受 members 数组，逐条调用 fill。
    payload: {year, quarter, members: [{userId, workHourScore, supervisorScore}, ...]}
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    members = payload.get("members") or []

    if not members:
        return {"success": False, "error": "empty members", "data": {}}

    ok = 0
    fail = 0
    errors = []
    for m in members:
        uid = str(m.get("userId", "")).strip()
        if not uid:
            fail += 1
            continue
        fill_payload = {
            "year": year,
            "quarter": quarter,
            "user_id": uid,
            "work_hour_score": m.get("workHourScore"),
            "supervisor_score": m.get("supervisorScore"),
        }
        # 支持手动覆盖上季结余/衰减
        if "prevCarryBalance" in m:
            fill_payload["prev_carry_balance"] = m.get("prevCarryBalance")
        if "prevDecayValue" in m:
            fill_payload["prev_decay_value"] = m.get("prevDecayValue")
        r = fill_member_input_service(fill_payload)
        if r.get("success"):
            ok += 1
        else:
            fail += 1
            errors.append({"userId": uid, "error": r.get("error")})

    return {
        "success": fail == 0,
        "data": {"ok": ok, "fail": fail, "errors": errors},
        "error": None if fail == 0 else f"{fail} members failed",
    }


def update_member_performance_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    全字段更新：输入字段 + 计算字段 + calcStatus，全部可改。
    传入哪个字段就更新哪个字段（null 视为清空该字段）。
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    user_id = str(payload.get("user_id") or payload.get("userId") or "").strip()
    if not user_id:
        return {"success": False, "error": "missing user_id", "data": {}}

    session = PerfSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        Model = _select_model_by_team_code(user_id)

        stmt = select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
        row = session.scalars(stmt).first()
        if not row:
            # 编辑模式下记录不存在 → 自动创建
            is_lead = _get_is_team_lead(user_id)
            row = Model(
                year=year,
                quarter=quarter,
                user_id=user_id,
                is_team_lead=is_lead,
                rule_code="default_rule_code",
                calc_status="filled",
                prev_carry_balance=0.0,
                prev_decay_value=0.0,
                final_score=0.0,
                new_carry_balance=0.0,
                carry_decay_value=0.0,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()

        # 字段名映射：前端 camelCase → 后端 ORM snake_case
        FIELD_MAP = {
            "workHourScore":     ("work_hour_score",     float),
            "supervisorScore":   ("supervisor_score",    float),
            "overallScore":      ("overall_score",       float),
            "prevCarryBalance":  ("prev_carry_balance",  float),
            "prevDecayValue":    ("prev_decay_value",    float),
            "compensationValue": ("compensation_value",  float),
            "overflowValue":     ("overflow_value",      float),
            "finalScore":        ("final_score",         float),
            "newCarryBalance":    ("new_carry_balance",   float),
            "carryDecayValue":   ("carry_decay_value",   float),
            "companyScore":      ("company_score",       float),
        }

        updated = 0
        for front_key, (col, cast) in FIELD_MAP.items():
            if front_key in payload:
                val = payload[front_key]
                setattr(row, col, cast(val) if val is not None else None)
                updated += 1

        # calcStatus 单独处理
        if "calcStatus" in payload:
            row.calc_status = str(payload["calcStatus"])
            updated += 1

        # prev_decay_value 恒为 prev_carry_balance * 0.25
        if row.prev_carry_balance is not None:
            row.prev_decay_value = float(_round3(Decimal(str(row.prev_carry_balance)) * Decimal("0.25")))

        # carry_decay_value 恒为 new_carry_balance * 0.25
        if row.new_carry_balance is not None:
            row.carry_decay_value = float(_round3(Decimal(str(row.new_carry_balance)) * Decimal("0.25")))

        if updated == 0:
            return {"success": False, "error": "no fields to update", "data": {}}

        row.updated_at = now
        session.commit()
        return {"success": True, "data": _row_to_dict(row)}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


# ── 统一团队 / 成员查询（供所有下拉条使用）──

def list_teams_service() -> Dict[str, Any]:
    """获取季度绩效 Scope 的固定团队选项（仅导航、对接）。"""
    teams = [
        {
            "teamCode": team.get("teamCode") or team.get("code"),
            "teamName": team.get("teamName") or team.get("name"),
        }
        for team in list_scope_teams("QUARTER_PERFORMANCE")["teams"]
        if (team.get("teamCode") or team.get("code")) in _TEAM_KEY_BY_CODE
    ]
    return {"success": True, "data": {"teams": teams}}


def list_members_service(payload: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    统一成员列表接口。可选 ?teamCode=NAV 过滤。
    """
    payload = payload or {}
    team_filter = str(payload.get("teamCode", "") or "").strip().upper() or None
    team_code = team_filter if team_filter in _TEAM_KEY_BY_CODE else None
    if team_filter and not team_code:
        return {"success": False, "error": f"unknown teamCode: {team_filter}", "data": {}}

    members = []
    for member in list_scope_members("QUARTER_PERFORMANCE", team_code):
        if member.get("teamCode") not in _TEAM_KEY_BY_CODE:
            continue
        members.append({
            "userId": member.get("userId"),
            "userName": member.get("userName") or member.get("userId"),
            "teamCode": member.get("teamCode"),
            "teamName": member.get("teamName") or "未分组",
            "jobRoleCode": member.get("jobRoleCode"),
            "jobRoleName": member.get("jobRoleName") or "未设置",
        })
    return {"success": True, "data": {"members": members, "count": len(members)}}


# ── 绩效历史查询（供 /dashboard/performance-history 使用）──


def performance_history_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    查询某用户全部季度的绩效记录，返回 PerformancePage 所需数据。
    """
    payload = payload or {}
    target = str(payload.get("target", "")).strip()

    uc_sess = SessionLocal()
    try:
        # 解析 target：可能是 user_id 或 name
        user_row = uc_sess.query(UserCharacter).filter(
            (UserCharacter.user_id == target) | (UserCharacter.name == target)
        ).first()

        if not user_row:
            return {"success": False, "error": "user not found", "data": {}}

        user_id = str(user_row.user_id)
        user_name = str(user_row.name or user_id)
        team_code = stable_team_code(getattr(user_row, "team_code", None))

        # 确定绩效表
        if team_code == "NAV":
            Model = NavPerfQuarterResult
        elif team_code == "INTEGRATION":
            Model = ServoPerfQuarterResult
        else:
            return {"success": False, "error": f"unknown team: {team_code}", "data": {}}

    finally:
        uc_sess.close()

    perf_sess = PerfSessionLocal()
    try:
        rows = (
            perf_sess.query(Model)
            .filter(Model.user_id == user_id)
            .filter(Model.calc_status.in_(["calculated", "archived"]))
            .order_by(Model.year.asc(), Model.quarter.asc())
            .all()
        )

        history = []
        for row in rows:
            overall = float(_round3(row.overall_score or 0))
            final = float(_round3(row.final_score or 0))
            carry = float(_round3(row.new_carry_balance or 0))
            overflow = float(_round3(row.overflow_value or 0))
            decay = float(_round3(row.carry_decay_value or 0))
            balance = float(_round3(overall + float(_round3(row.prev_carry_balance or 0))))

            history.append({
                "quarter": f"{row.year} Q{row.quarter}",
                "hourScore": float(_round3(row.work_hour_score or 0)),
                "managerScore": float(_round3(row.supervisor_score or 0)),
                "overallScore": overall,
                "balanceScore": balance,
                "overflowScore": overflow,
                "decayScore": decay,
                "carryScore": carry,
                "finalScore": final,
            })

        return {
            "success": True,
            "data": {
                "targetLabel": user_name,
                "selectedTarget": user_id,
                "desc": f"{user_name} · 季度绩效归档视图 · 最终绩效决定正式档位",
                "history": history,
            },
        }
    finally:
        perf_sess.close()
