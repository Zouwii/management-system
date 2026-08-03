"""
A 表 project_tasks：列表同步快照。
B 表 project_task_details：模式 1 — UNIQUE(task_id, query_user_id)，每次覆盖更新。
sync_runs：可选，列表 / 明细批次同步元数据（对账、排障）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProjectTask(Base):
    __tablename__ = "project_tasks"
    __table_args__ = (UniqueConstraint("project_id", "task_id", name="uq_project_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, default="")
    scenario_field_config_id: Mapped[str] = mapped_column(String(64), default="")
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    taskflow_status_id: Mapped[str] = mapped_column(String(64), default="")

    executor_id: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[str] = mapped_column(String(64), default="")

    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_created: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[str] = mapped_column(String(32), default="members")

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    customfield_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProgramIssue(Base):
    __tablename__ = "program_issue"
    __table_args__ = (UniqueConstraint("project_id", "task_id", name="uq_program_issue_project_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, default="")
    scenario_field_config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    taskflow_status_id: Mapped[str] = mapped_column(String(64), default="")

    executor_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    creator_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accomplished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_created: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ding_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[str] = mapped_column(String(32), default="members")

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    customfield_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectTaskDetail(Base):
    """模式 1：(task_id, query_user_id) 唯一，新拉取覆盖该行。"""

    __tablename__ = "project_task_details"
    __table_args__ = (
        UniqueConstraint("task_id", "query_user_id", name="uq_task_query_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario_field_config_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    work_hour_field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    requirement_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_outputs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    task_nature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    need_statistic: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    workday_costhour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # 是否逾期（由 tagIds 判断）
    is_overdue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 业务类型：0=产品，1=研发，2=订单
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # 任务状态映射值：0..N（由 taskflowStatusId 映射）
    task_flow_status_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # 级联自定义字段解析（customFieldId=665ee4b45b46f34b3e045af2）
    project_category_1: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vehicle_type_2: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    project_name_3: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProgramIssueDetail(Base):
    """问题处理详情表：(task_id, query_user_id) 唯一，新拉取覆盖该行。"""

    __tablename__ = "program_issue_detail"
    __table_args__ = (
        UniqueConstraint("task_id", "query_user_id", name="uq_program_issue_task_query_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    scenario_field_config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    executor_id: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[str] = mapped_column(String(64), default="")
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    taskflow_status_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_nature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    need_statistic: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    workday_costhour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    work_hour_field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visible: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at_ding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_ding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 级联自定义字段解析（customFieldId=665ee4b45b46f34b3e045af2）
    project_category_1: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vehicle_type_2: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    project_name_3: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)


class ProjectTaskOverdueDetail(Base):
    """
    C 表 project_task_overdue_details：逾期明细快照（用于“季度逾期”等统计口径）。

    约束：同一个 (project_id, task_id, query_user_id) 只保留一行，按同步覆盖。
    """

    __tablename__ = "project_task_overdue_details"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "task_id",
            "query_user_id",
            name="uq_overdue_project_task_query_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scenario_field_config_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 业务类型：0=产品，1=研发，2=订单
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # 任务状态映射值：0..N（由 taskflowStatusId 映射）
    task_flow_status_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_nature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    need_statistic: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    workday_costhour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 级联自定义字段解析（customFieldId=665ee4b45b46f34b3e045af2）
    project_category_1: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vehicle_type_2: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    project_name_3: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SyncRun(Base):
    """同步批次：便于排查「这次列表写了多少条」「明细批次是否失败」。"""

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SyncFailure(Base):
    """同步失败明细表：用于追踪最终失败的 task/executor/error。"""

    __tablename__ = "sync_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    phase: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    executor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    retry_round: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)


class Config(Base):
    """
    数据库配置表（参照你其它任务的 config 表）

    只有四列：id，type，value，brief
    """

    __tablename__ = "config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 避免在代码里用关键字 type 作为属性名；数据库列名仍为 type
    type_: Mapped[str] = mapped_column("type", String(64), nullable=False, index=True, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    brief: Mapped[Optional[str]] = mapped_column(Text, default=None)


class UpdateLock(Base):
    """
    更新互斥锁（数据库锁）：
    - lock_key：锁粒度（例如 workhour_update:all）
    - owner：持有者标识（userId + timestamp）
    - expires_at：过期时间，防止异常退出导致死锁
    """

    __tablename__ = "update_locks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lock_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class UserCharacter(Base):
    """
    用户维度的 character 配置表（供你之后手动填充）

    字段：
    - 中文名：name
    - 钉钉用户 id：user_id
    - character：character（1/2/3/4）
    """

    __tablename__ = "user_character"

    # 以钉钉用户 id 作为唯一主键，方便后续 upsert
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    character: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 组别归属（用于绩效数据的归属判断）
    team_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)

    # 组长标记：导航组/对接组是否为组长
    is_nav_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_servo_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 钉钉 unionId（OAuth 登录后回填，用于知识库 API 调用等场景）
    union_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, default=None)


class _PerfQuarterResultMixin:
    """nav/servo 两张绩效表共享的列定义（21列：标识10 + 输入2 + 计算9）。"""

    # =========================
    # 标识层（10 列）
    # =========================
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    is_team_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 身份快照
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default_rule_code")
    calc_status: Mapped[str] = mapped_column(String(32), nullable=False, default="filled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)

    # =========================
    # 输入层（2 列）
    # =========================
    work_hour_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    supervisor_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # =========================
    # 计算层（9 列）
    # =========================
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prev_carry_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)   # 上季 new_carry
    prev_decay_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)      # 上季 carry_decay
    compensation_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overflow_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    new_carry_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    carry_decay_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    company_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class NavPerfQuarterResult(_PerfQuarterResultMixin, Base):
    """导航组绩效结果表。"""

    __tablename__ = "nav_perf_quarter_result"
    __table_args__ = (UniqueConstraint("year", "quarter", "user_id", name="uq_nav_perf_quarter_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class ServoPerfQuarterResult(_PerfQuarterResultMixin, Base):
    """对接组绩效结果表。"""

    __tablename__ = "servo_perf_quarter_result"
    __table_args__ = (UniqueConstraint("year", "quarter", "user_id", name="uq_servo_perf_quarter_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)


class MemberAttendance(Base):
    """员工出勤调整表：按用户+季度持久化加班/请假天数。

    前端 员工出勤表 中的加班/请假字段持久化存储，
    同一用户+同一季度只保留一条记录，保存时 upsert 覆盖。
    """

    __tablename__ = "member_attendance"
    __table_args__ = (UniqueConstraint("user_id", "year", "quarter", name="uq_member_attendance_user_quarter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    team_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    overtime_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    leave_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)


class ApiCallLog(Base):
    """钉钉 API 调用日志（持久化统计）。"""

    __tablename__ = "api_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    error_msg: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


# ─────────────────────────────────────────────────────────────
# onsite_problem A/B 表
# ─────────────────────────────────────────────────────────────


class OnsiteProblemTask(Base):
    """现场问题跟踪 — A 表：列表快照。"""

    __tablename__ = "onsite_problem_tasks"
    __table_args__ = (UniqueConstraint("project_id", "task_id", name="uq_onsite_problem_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, default="")
    scenario_field_config_id: Mapped[str] = mapped_column(String(64), default="")
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    task_list_id: Mapped[str] = mapped_column(String(64), default="")
    task_stage_id: Mapped[str] = mapped_column(String(64), default="")
    taskflow_status_id: Mapped[str] = mapped_column(String(64), default="")

    executor_id: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[str] = mapped_column(String(64), default="")

    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_created: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[str] = mapped_column(String(32), default="members")

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    customfield_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class OnsiteProblemDetail(Base):
    """现场问题跟踪 — B 表：任务明细，解析关键 customField。"""

    __tablename__ = "onsite_problem_details"
    __table_args__ = (UniqueConstraint("task_id", "query_user_id", name="uq_onsite_problem_detail"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    creator_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scenario_field_config_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    taskflow_status_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_done: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_archived: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visible: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)

    # ── 拆列：customField 解析 ──
    # ── 解析后的 customField ──
    # 基础模板
    vehicle_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)    # 车型 (659369d3)
    carrier_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)      # 载具配置 (637c2e2f)
    occurrence_frequency: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 复现概率 (62c51d82)
    software_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # JZTOTAL包版本 (6645bd4d)
    problem_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)      # 问题描述 (624e4bf0)
    investigation_conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # 排查结论 (69241440)
    doc_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                # 排查文档价值 (69241431)
    investigation_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True) # 排查文档 (69241391)
    attachments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)              # 其他附件信息 (625f75e9)
    # 扩展模板
    problem_category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # 问题类型分类 (691a9554)
    problem_module: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)     # 问题模块分类 (691a95f3)
    guide_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # 指导文档 (62651ead)
    formal_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # 正式版本 (625f8339)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)               # 原因分析 (625f8317)
    solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                 # 解决方案 (625f8329)
    submitter: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)          # 提交者 (68f63735)

    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── 评论流 + 附件流（TB Open API via proxy，2026-07-24）──
    comments_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    attachments_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ReqPoolTask(Base):
    """需求池 — A 表：列表快照。"""

    __tablename__ = "req_pool_tasks"
    __table_args__ = (UniqueConstraint("project_id", "task_id", name="uq_req_pool_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, default="")
    scenario_field_config_id: Mapped[str] = mapped_column(String(64), default="")
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    task_list_id: Mapped[str] = mapped_column(String(64), default="")
    task_stage_id: Mapped[str] = mapped_column(String(64), default="")
    taskflow_status_id: Mapped[str] = mapped_column(String(64), default="")

    executor_id: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[str] = mapped_column(String(64), default="")

    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_created: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[str] = mapped_column(String(32), default="members")

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    customfield_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ReqPoolDetail(Base):
    """需求池 — B 表：任务明细，解析关键 customField。"""

    __tablename__ = "req_pool_details"
    __table_args__ = (UniqueConstraint("task_id", "query_user_id", name="uq_req_pool_detail"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    executor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    creator_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scenario_field_config_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    taskflow_status_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_done: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    is_archived: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    visible: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)

    # ── 拆列：customField 解析 ──
    req_source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    release_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    package_version: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prd_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dev_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_case: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    biz_owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    comments_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    attachments_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

# ─────────────────────────────────────────────────────────────
# 算法组 A/B 表（两个项目共享同一套表结构）
# ─────────────────────────────────────────────────────────────


class AlgoTask(Base):
    """算法组软件开发 A 表；字段结构与 ProjectTask 一致。"""

    __tablename__ = "algo_tasks"
    __table_args__ = (UniqueConstraint("project_id", "task_id", name="uq_algo_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, default="")
    scenario_field_config_id: Mapped[str] = mapped_column(String(64), default="")
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    taskflow_status_id: Mapped[str] = mapped_column(String(64), default="")

    executor_id: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[str] = mapped_column(String(64), default="")

    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_created: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[str] = mapped_column(String(32), default="members")

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    customfield_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AlgoTaskDetail(Base):
    """算法组软件开发 B 表；字段结构与 ProjectTaskDetail 一致。"""

    __tablename__ = "algo_task_details"
    __table_args__ = (
        UniqueConstraint("task_id", "query_user_id", name="uq_algo_task_detail"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    scenario_field_config_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    work_hour_field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    requirement_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_outputs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    task_nature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    need_statistic: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    workday_costhour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    is_overdue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    task_flow_status_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    project_category_1: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vehicle_type_2: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    project_name_3: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AlgoIssue(Base):
    """算法组问题处理 A 表；字段结构与 ProgramIssue 一致。"""

    __tablename__ = "algo_issues"
    __table_args__ = (UniqueConstraint("project_id", "task_id", name="uq_algo_issue"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    content: Mapped[str] = mapped_column(Text, default="")
    scenario_field_config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage_id: Mapped[str] = mapped_column(String(64), default="")
    taskflow_status_id: Mapped[str] = mapped_column(String(64), default="")

    executor_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    creator_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    accomplished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ding_created: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    ding_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[str] = mapped_column(String(32), default="members")

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    labels: Mapped[Optional[List[Any]]] = mapped_column(JSON, nullable=True)
    customfield_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    list_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AlgoIssueDetail(Base):
    """算法组问题处理 B 表；字段结构与 ProgramIssueDetail 一致。"""

    __tablename__ = "algo_issue_details"
    __table_args__ = (
        UniqueConstraint("task_id", "query_user_id", name="uq_algo_issue_detail"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    scenario_field_config_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, default="")
    executor_id: Mapped[str] = mapped_column(String(64), default="")
    creator_id: Mapped[str] = mapped_column(String(64), default="")
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    taskflow_status_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    task_nature: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    need_statistic: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    workday_costhour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    work_hour_field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    priority: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    visible: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    created_at_ding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at_ding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    ancestor_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    involve_members: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tag_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project_category_1: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vehicle_type_2: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    project_name_3: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)
