"""
钉钉「单任务查询」接口返回里 result[] 单条明细的标准形状。

对应业务：POST/GET .../users/{userId}/tasks?taskId=...

与「项目任务列表」models/dingtalk_project_task.py 的差异（摘要）：
- 自定义字段键名：列表常为 `customfields` + `customfieldId` 且无 `value`；
  明细为 `customFields` + `customFieldId`，并带 `type` 与 `value`（数组，内含 title/metaString 等）。
- 明细常见调度/层级字段：parentTaskId、taskListId、taskStageId、uniqueId；
  列表常见 stageId，未必带 parentTaskId / taskListId / uniqueId。
- 列表常有 progress、isDeleted 等；明细可能缺省，解析时用默认值。

明细里 `value` 结构随 type（rtf / dropDown / lookup2 / number 等）变化，故保留为结构化 + 原始 list[dict] 便于落 JSON。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DingTalkCustomFieldDetail:
    """单条自定义字段定义（含类型与取值，对应钉钉 customFields[] 一项）。"""

    custom_field_id: str
    field_type: str
    value: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DingTalkCustomFieldDetail":
        fid = d.get("customFieldId") or d.get("customfieldId") or ""
        ftype = str(d.get("type") or "")
        raw_val = d.get("value")
        if raw_val is None:
            vals: List[Dict[str, Any]] = []
        elif isinstance(raw_val, list):
            vals = [x for x in raw_val if isinstance(x, dict)]
        elif isinstance(raw_val, dict):
            vals = [raw_val]
        else:
            vals = []
        return cls(custom_field_id=str(fid), field_type=ftype, value=vals)


@dataclass
class DingTalkTaskDetailRow:
    """
    与明细接口单条任务对齐（Python snake_case）。

    主键业务键仍以 task_id + project_id 为主；unique_id 为钉钉数字 uniqueId（若存在）。
    """

    task_id: str
    project_id: str
    content: str
    scenario_field_config_id: str
    taskflow_status_id: str
    executor_id: str
    creator_id: str

    task_stage_id: str = ""
    task_list_id: str = ""
    parent_task_id: Optional[str] = None
    unique_id: Optional[int] = None

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

    custom_fields: List[DingTalkCustomFieldDetail] = field(default_factory=list)

    fetched_at: Optional[str] = None
    raw_json: Optional[str] = None

    @classmethod
    def from_api_dict(cls, d: Dict[str, Any]) -> "DingTalkTaskDetailRow":
        cfs = d.get("customFields") or d.get("customfields") or []
        details: List[DingTalkCustomFieldDetail] = []
        if isinstance(cfs, list):
            for item in cfs:
                if isinstance(item, dict):
                    details.append(DingTalkCustomFieldDetail.from_dict(item))

        uid = d.get("uniqueId")
        unique_id: Optional[int]
        if uid is None or uid == "":
            unique_id = None
        else:
            try:
                unique_id = int(uid)
            except (TypeError, ValueError):
                unique_id = None

        def _str_list(key: str) -> List[str]:
            v = d.get(key)
            if not isinstance(v, list):
                return []
            return [str(x) for x in v if x is not None]

        return cls(
            task_id=str(d.get("taskId") or ""),
            project_id=str(d.get("projectId") or ""),
            content=str(d.get("content") or ""),
            scenario_field_config_id=str(
                d.get("scenarioFieldConfigId") or d.get("scenariofieldconfigId") or ""
            ),
            taskflow_status_id=str(
                d.get("taskflowStatusId") or d.get("taskflowstatusId") or ""
            ),
            executor_id=str(d.get("executorId") or ""),
            creator_id=str(d.get("creatorId") or ""),
            task_stage_id=str(d.get("taskStageId") or d.get("stageId") or ""),
            task_list_id=str(d.get("taskListId") or ""),
            parent_task_id=_opt_str(d.get("parentTaskId")),
            unique_id=unique_id,
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
            custom_fields=details,
        )

    def to_flat_dict(self) -> Dict[str, Any]:
        """扁平 dict；custom_fields 展开为可 JSON 序列化的结构。"""

        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "content": self.content,
            "scenario_field_config_id": self.scenario_field_config_id,
            "taskflow_status_id": self.taskflow_status_id,
            "executor_id": self.executor_id,
            "creator_id": self.creator_id,
            "task_stage_id": self.task_stage_id,
            "task_list_id": self.task_list_id,
            "parent_task_id": self.parent_task_id,
            "unique_id": self.unique_id,
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
            "custom_fields": [
                {
                    "custom_field_id": c.custom_field_id,
                    "field_type": c.field_type,
                    "value": list(c.value),
                }
                for c in self.custom_fields
            ],
        }


def _opt_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
