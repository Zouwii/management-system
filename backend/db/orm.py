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

    work_hour_field_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_task_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_list_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    task_stage_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    unique_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 是否逾期（由 tagIds 判断）
    is_overdue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 业务类型：0=产品，1=研发，2=订单
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # 任务状态映射值：0..N（由 taskflowStatusId 映射）
    task_flow_status_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


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

    work_hour: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 业务类型：0=产品，1=研发，2=订单
    business_type: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # 任务状态映射值：0..N（由 taskflowStatusId 映射）
    task_flow_status_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    custom_fields_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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


class _PerfQuarterResultMixin:
    """nav/servo 两张绩效表共享的列定义。"""

    # 基本定位
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    team_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # 角色与规则口径
    role_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # employee / manager
    is_team_lead: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rule_code: Mapped[str] = mapped_column(String(64), nullable=False, default="default_rule_code")

    calc_status: Mapped[str] = mapped_column(String(32), nullable=False, default="filled")

    # 审计时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.now)

    # =========================
    # 输入（主管填写/系统取数）
    # =========================
    work_hour_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    supervisor_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    okr_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    team_avg_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # =========================
    # 总体与区间辅助（用于 finalScore 解释）
    # =========================
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    compensation_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overflow_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # =========================
    # 跨季度结余衔接（用于下一季度 prev）
    # =========================
    prev_carry_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    prev_decay_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    carry_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    new_carry_balance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    carry_decay_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # =========================
    # 最终输出（finalScore）
    # =========================
    final_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    company_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    carry_calc_mode: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    calc_trace_json: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)


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
