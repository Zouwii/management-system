"""
钉钉「查询项目下任务」接口返回里 result[] 单条任务的标准形状。

对应 HTTP：GET .../projectIds/{projectId}/tasks
典型字段见钉钉文档与你们线上返回（customfields 常为仅含 customfieldId 的占位项）。

后续落库建议（二选一）：
- 宽表 + JSON 列：ancestor_ids / involve_members / tag_ids / customfields 存 JSON 文本；
- 规范化：本表存任务主数据，子表存 task_custom_field(task_id, customfield_id)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DingTalkCustomFieldRef:
    """列表接口里常见的自定义字段占位：往往只有 customfieldId，无 value。"""

    customfield_id: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DingTalkCustomFieldRef":
        cid = d.get("customfieldId") or d.get("customFieldId") or ""
        return cls(customfield_id=str(cid))


@dataclass
class DingTalkProjectTaskRow:
    """
    与钉钉返回单条任务对齐（字段名采用 Python snake_case，便于 ORM/建表）。

    主键候选：task_id（业务上唯一）；联合 (project_id, task_id) 亦可。
    """

    task_id: str
    project_id: str
    content: str
    scenario_field_config_id: str
    stage_id: str
    taskflow_status_id: str
    executor_id: str
    creator_id: str
    due_date: Optional[str] = None
    created: Optional[str] = None
    updated: Optional[str] = None
    note: str = ""
    priority: int = 0
    progress: int = 0
    visible: str = "members"
    is_archived: bool = False
    is_deleted: bool = False
    is_done: bool = False
    ancestor_ids: List[str] = field(default_factory=list)
    involve_members: List[str] = field(default_factory=list)
    tag_ids: List[str] = field(default_factory=list)
    labels: List[Any] = field(default_factory=list)
    customfields: List[DingTalkCustomFieldRef] = field(default_factory=list)

    # 同步元数据（入库时由你们写入，非钉钉原样字段）
    synced_at: Optional[str] = None
    raw_json: Optional[str] = None

    @classmethod
    def from_api_dict(cls, d: Dict[str, Any]) -> "DingTalkProjectTaskRow":
        cfs = d.get("customfields") or d.get("customFields") or []
        refs: List[DingTalkCustomFieldRef] = []
        if isinstance(cfs, list):
            for item in cfs:
                if isinstance(item, dict):
                    refs.append(DingTalkCustomFieldRef.from_dict(item))

        def _str_list(key: str) -> List[str]:
            v = d.get(key)
            if not isinstance(v, list):
                return []
            out: List[str] = []
            for x in v:
                if x is None:
                    continue
                out.append(str(x))
            return out

        return cls(
            task_id=str(d.get("taskId") or ""),
            project_id=str(d.get("projectId") or ""),
            content=str(d.get("content") or ""),
            scenario_field_config_id=str(
                d.get("scenariofieldconfigId") or d.get("scenarioFieldConfigId") or ""
            ),
            stage_id=str(d.get("stageId") or ""),
            taskflow_status_id=str(
                d.get("taskflowstatusId") or d.get("taskflowStatusId") or ""
            ),
            executor_id=str(d.get("executorId") or ""),
            creator_id=str(d.get("creatorId") or ""),
            due_date=_opt_str(d.get("dueDate")),
            created=_opt_str(d.get("created")),
            updated=_opt_str(d.get("updated")),
            note=str(d.get("note") or ""),
            priority=int(d.get("priority") or 0),
            progress=int(d.get("progress") or 0),
            visible=str(d.get("visible") or "members"),
            is_archived=bool(d.get("isArchived")),
            is_deleted=bool(d.get("isDeleted")),
            is_done=bool(d.get("isDone")),
            ancestor_ids=_str_list("ancestorIds"),
            involve_members=_str_list("involveMembers"),
            tag_ids=_str_list("tagIds"),
            labels=d.get("labels") if isinstance(d.get("labels"), list) else [],
            customfields=refs,
        )

    def to_flat_dict(self) -> Dict[str, Any]:
        """扁平 dict，便于 JSON 列或与 ORM 映射（数组仍以 list 形式）。"""

        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "content": self.content,
            "scenario_field_config_id": self.scenario_field_config_id,
            "stage_id": self.stage_id,
            "taskflow_status_id": self.taskflow_status_id,
            "executor_id": self.executor_id,
            "creator_id": self.creator_id,
            "due_date": self.due_date,
            "created": self.created,
            "updated": self.updated,
            "note": self.note,
            "priority": self.priority,
            "progress": self.progress,
            "visible": self.visible,
            "is_archived": self.is_archived,
            "is_deleted": self.is_deleted,
            "is_done": self.is_done,
            "ancestor_ids": list(self.ancestor_ids),
            "involve_members": list(self.involve_members),
            "tag_ids": list(self.tag_ids),
            "labels": list(self.labels),
            "customfield_ids": [c.customfield_id for c in self.customfields],
        }


def _opt_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
