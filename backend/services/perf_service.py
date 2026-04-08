from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select

from db.engine import PerfSessionLocal
from db.orm import NavPerfQuarterResult, ServoPerfQuarterResult, UserCharacter


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
    # 成员规则：overall = ROUND(hour*0.7 + supervisor*0.3, 3)
    hour = Decimal(str(work_hour_score or 0))
    sup = Decimal(str(supervisor_score or 0))
    raw = hour * Decimal("0.7") + sup * Decimal("0.3")
    return _round3(raw)


def _threshold_interval_by_overall(overall_score: Decimal) -> Tuple[Decimal, Decimal]:
    """
    根据文档“区间上限/区间下限”确定当前档位的下限/下一档上限。

    区间（与补偿/溢出定义一致）：
    [0, 0.8)   -> lower=0,   upper=0.8
    [0.8, 1)   -> lower=0.8, upper=1.0
    [1.0, 1.2) -> lower=1.0, upper=1.2
    [1.2, 1.5) -> lower=1.2, upper=1.5
    [1.5, 2.0) -> lower=1.5, upper=2.0
    [2.0, +inf)-> lower=2.0, upper=2.0  (最后一档无“下一档”)
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
    # 与文档“绩效档位映射表”一致（difficulty -> company_score）
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


def fill_member_input_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    主管输入（成员规则）：写入 perf_quarter_result 的输入列（work_hour_score/supervisor_score等）。
    只填充不计算：calc_status 置为 filled。
    """
    payload = payload or {}
    year = int(payload.get("year"))
    quarter = int(payload.get("quarter"))
    user_id = str(payload.get("user_id") or payload.get("userId") or payload.get("userid") or "").strip()
    if not user_id:
        return {"success": False, "error": "missing user_id", "data": {}}

    hour_score = payload.get("work_hour_score", payload.get("hour_score", payload.get("hourScore")))
    manager_score = payload.get("supervisor_score", payload.get("manager_score", payload.get("managerScore")))
    if hour_score is None or manager_score is None:
        return {"success": False, "error": "missing hour_score or manager_score", "data": {}}

    now = datetime.now(timezone.utc)
    session = PerfSessionLocal()
    try:
        # 根据 user_character.team_id 决定写入 nav/servo 哪张表
        c_row = session.query(UserCharacter).filter(UserCharacter.user_id == user_id).first()
        if not c_row or not getattr(c_row, "team_id", None):
            return {"success": False, "error": "missing user_character.team_id for user", "data": {}}

        team_id = str(c_row.team_id)

        def _select_model(tid: str):
            # 兼容可能的取值：nav/servo，或 1/2
            if tid in {"nav", "1", "navigation"}:
                return NavPerfQuarterResult
            if tid in {"servo", "2", "service", "对接", "servo_team"}:
                return ServoPerfQuarterResult
            raise ValueError(f"unsupported team_id: {tid}")

        Model = _select_model(team_id)

        stmt = select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
        row = session.scalars(stmt).first()
        if row:
            row.user_name = payload.get("user_name", payload.get("userName")) or row.user_name
            row.team_id = str(payload.get("team_id") or payload.get("teamId") or "") or row.team_id
            row.team_name = payload.get("team_name", payload.get("teamName")) or row.team_name
            row.role_type = "employee"
            row.is_team_lead = False
            row.rule_code = payload.get("rule_code", payload.get("ruleCode")) or row.rule_code
            row.work_hour_score = float(hour_score)
            row.supervisor_score = float(manager_score)
            row.calc_status = "filled"
            row.updated_at = now
        else:
            row = Model(
                year=year,
                quarter=quarter,
                user_id=user_id,
                user_name=payload.get("user_name", payload.get("userName")),
                team_id=str(payload.get("team_id") or payload.get("teamId") or "") or team_id,
                team_name=payload.get("team_name", payload.get("teamName")),
                role_type="employee",
                is_team_lead=False,
                rule_code=payload.get("rule_code", payload.get("ruleCode")) or "default_rule_code",
                calc_status="filled",
                work_hour_score=float(hour_score),
                supervisor_score=float(manager_score),
                created_at=now,
                updated_at=now,
            )
            session.add(row)

        session.commit()
        return {"success": True, "data": {"id": row.id, "calc_status": row.calc_status}}
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()


def calculate_member_quarter_performance_service(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    计算（成员规则）：根据本季度输入 + 上季度结余/衰减，计算：
    - overall_score
    - 补偿/溢出/区间上下限
    - final_score
    - new_carry_balance / carry_decay_value
    并回写到 perf_quarter_result。
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
        # 根据 user_character.team_id 决定从 nav/servo 哪张表取数
        c_row = session.query(UserCharacter).filter(UserCharacter.user_id == user_id).first()
        if not c_row or not getattr(c_row, "team_id", None):
            return {"success": False, "error": "missing user_character.team_id for user", "data": {}}
        team_id = str(c_row.team_id)

        def _select_model(tid: str):
            if tid in {"nav", "1", "navigation"}:
                return NavPerfQuarterResult
            if tid in {"servo", "2", "service", "对接", "servo_team"}:
                return ServoPerfQuarterResult
            raise ValueError(f"unsupported team_id: {tid}")

        Model = _select_model(team_id)

        stmt = select(Model).where(Model.year == year, Model.quarter == quarter, Model.user_id == user_id)
        row = session.scalars(stmt).first()
        if not row:
            return {"success": False, "error": "perf_quarter_result not found (need fill first)", "data": {}}

        if bool(row.is_team_lead):
            return {"success": False, "error": "this endpoint only supports member(is_team_lead=false)", "data": {}}

        if row.work_hour_score is None or row.supervisor_score is None:
            return {"success": False, "error": "missing input hour_score/manager_score", "data": {}}

        prev_year, prev_quarter = _prev_year_quarter(year, quarter)
        prev_stmt = select(Model).where(Model.year == prev_year, Model.quarter == prev_quarter, Model.user_id == user_id)
        prev_row = session.scalars(prev_stmt).first()

        prev_carry_balance = _round3((prev_row.new_carry_balance if prev_row and prev_row.new_carry_balance is not None else 0.0))
        prev_decay_value = _round3((prev_row.carry_decay_value if prev_row and prev_row.carry_decay_value is not None else 0.0))

        overall_score = _member_overall_score(row.work_hour_score, row.supervisor_score)
        interval_lower, interval_upper = _threshold_interval_by_overall(overall_score)

        compensation_value = _round3(overall_score - interval_upper)  # 离下一档还差多少（通常为负）
        overflow_value = _round3(overall_score - interval_lower)  # 当前档内超出多少（>=0）

        # 结余绩效（展示核对用）
        carry_score = _round3(overall_score + prev_carry_balance)

        can_upgrade = (prev_carry_balance + compensation_value) >= Decimal("0")
        if can_upgrade:
            final_score = interval_upper
            raw = prev_carry_balance + compensation_value - prev_decay_value
            new_carry_balance = _round3(raw) if raw >= Decimal("0") else Decimal("0.000")
            carry_calc_mode = "upgrade_then_decay"
        else:
            final_score = interval_lower
            new_carry_balance = _round3(prev_carry_balance * Decimal("0.75") + overflow_value)
            carry_calc_mode = "decay_then_add_overflow"

        carry_decay_value = _round3(new_carry_balance * Decimal("0.25"))
        company_score = _map_company_score(final_score)

        row.overall_score = float(overall_score)
        row.threshold_lower = float(interval_lower)
        row.threshold_upper = float(interval_upper)
        row.compensation_value = float(compensation_value)
        row.overflow_value = float(overflow_value)

        row.prev_carry_balance = float(prev_carry_balance)
        row.prev_decay_value = float(prev_decay_value)
        row.carry_score = float(carry_score)

        row.final_score = float(final_score)
        row.company_score = float(company_score)
        row.new_carry_balance = float(new_carry_balance)
        row.carry_decay_value = float(carry_decay_value)
        row.carry_calc_mode = carry_calc_mode

        row.calc_status = "calculated"
        row.updated_at = now

        row.calc_trace_json = {
            "overall_score": float(overall_score),
            "interval_lower": float(interval_lower),
            "interval_upper": float(interval_upper),
            "compensation_value": float(compensation_value),
            "overflow_value": float(overflow_value),
            "prev_carry_balance": float(prev_carry_balance),
            "prev_decay_value": float(prev_decay_value),
            "can_upgrade": bool(can_upgrade),
            "carry_calc_mode": carry_calc_mode,
            "new_carry_balance": float(new_carry_balance),
            "carry_decay_value": float(carry_decay_value),
        }

        session.commit()
        return {
            "success": True,
            "data": {
                "overallScore": row.overall_score,
                "finalScore": row.final_score,
                "newCarryBalance": row.new_carry_balance,
                "carryDecayValue": row.carry_decay_value,
                "calcMode": row.carry_calc_mode,
            },
        }
    except Exception as e:
        session.rollback()
        return {"success": False, "error": str(e), "data": {}}
    finally:
        session.close()

