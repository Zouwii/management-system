"""从钉钉任务详情 dict 中解析指定自定义字段的数值工时（与前端逻辑一致）。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


def parse_workhour_from_task_dict(task: Dict[str, Any], target_field_id: str) -> Optional[float]:
    fields = task.get("customFields") or task.get("customfields") or []
    if not isinstance(fields, list):
        return None
    for f in fields:
        if not isinstance(f, dict):
            continue
        fid = f.get("customFieldId") or f.get("customfieldId")
        if str(fid or "") != str(target_field_id):
            continue
        return _parse_value_to_float(f.get("value"))
    return None


def _parse_value_to_float(vals: Any) -> Optional[float]:
    if vals is None:
        return None
    if isinstance(vals, str):
        try:
            vals = json.loads(vals)
        except Exception:
            vals = []
    if isinstance(vals, list) and len(vals) > 0:
        v0 = vals[0] if isinstance(vals[0], dict) else {}
        x = v0.get("title", v0.get("value", v0.get("numberValue")))
        return _to_float(x)
    if isinstance(vals, dict):
        x = vals.get("title", vals.get("value"))
        return _to_float(x)
    return _to_float(vals)


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x) if isinstance(x, float) or isinstance(x, int) else None
    if isinstance(x, str):
        m = re.search(r"-?\d+(\.\d+)?", x)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
        try:
            return float(x)
        except ValueError:
            return None
    return None
