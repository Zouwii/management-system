"""
领域模型与 API 载荷结构（与后续数据库表对齐时可复用字段名）。
"""

from .dingtalk_project_task import (
    DingTalkCustomFieldRef,
    DingTalkProjectTaskRow,
)
from .dingtalk_task_detail import (
    DingTalkCustomFieldDetail,
    DingTalkTaskDetailRow,
)

__all__ = [
    "DingTalkCustomFieldRef",
    "DingTalkProjectTaskRow",
    "DingTalkCustomFieldDetail",
    "DingTalkTaskDetailRow",
]
