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
