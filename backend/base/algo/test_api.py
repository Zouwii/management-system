"""深度检查 - 查找有自定义字段的任务"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json, requests, time

from base.dingtalk_client import get_valid_access_token

ALGO_PROJECTS = [
    ("算法开发", "636f343d3997deea0514c030", "636f343df27cfe0042368b30"),
    ("算法问题", "636f31a87ef5737c3e837d00", "636f31a8708ae400405aaaab"),
]

ALGO_MEMBER_IDS = [
    "0525436259671512", "2464543025951000", "555363695138848564",
    "22665556381168535", "2409506118778941",
]

def deep_inspect(name, pid, sfid):
    print(f"\n{'='*60}")
    print(f"项目: {name}")
    print(f"{'='*60}")
    
    token_result = get_valid_access_token({})
    if not token_result.get("ok"):
        return
    token = token_result["access_token"]
    headers = {"x-acs-dingtalk-access-token": token, "Content-Type": "application/json"}
    
    # 所有成员的列表
    all_tasks = []
    for uid in ALGO_MEMBER_IDS:
        url = f"https://api.dingtalk.com/v1.0/project/users/{uid}/projectIds/{pid}/tasks"
        resp = requests.get(url, headers=headers, params={"maxResults": 50}, timeout=15)
        if resp.status_code == 200:
            items = resp.json().get("result", [])
            for it in items:
                sid = it.get("scenarioFieldConfigId") or it.get("scenariofieldconfigId") or ""
                if sid == sfid:
                    all_tasks.append(it)
        time.sleep(0.2)
    
    # 去重
    seen = set()
    uniq = []
    for t in all_tasks:
        tid = t.get("taskId","")
        if tid not in seen:
            seen.add(tid)
            uniq.append(t)
    
    print(f"  去重后任务: {len(uniq)} 条")
    print(f"  undone: {sum(1 for t in uniq if not t.get('isDone'))}")
    print(f"  done:   {sum(1 for t in uniq if t.get('isDone'))}")
    print(f"  archived: {sum(1 for t in uniq if t.get('isArchived'))}")
    
    # 检查3条详情看 customFields
    has_cf = 0
    no_cf = 0
    for t in uniq[:5]:
        tid = t.get("taskId")
        url_d = f"https://api.dingtalk.com/v1.0/project/users/{t.get('executorId')}/tasks"
        dresp = requests.get(url_d, headers=headers, params={"taskId": tid}, timeout=15)
        if dresp.status_code == 200:
            raw = dresp.json().get("result", [])
            item = raw[0] if raw else {}
            cfs = item.get("customFields", [])
            if cfs:
                has_cf += 1
                print(f"    有自定义字段: {t.get('content','')[:50]} → {len(cfs)} fields")
                for cf in cfs[:8]:
                    print(f"      [{cf.get('customFieldId','')}] {cf.get('customFieldName','')}")
            else:
                no_cf += 1
        time.sleep(0.1)
    
    print(f"  有CF: {has_cf}, 无CF: {no_cf}")
    
    # 统计 executor_id 分布
    exe_count = {}
    for t in uniq:
        ex = t.get("executorId","unknown")
        exe_count[ex] = exe_count.get(ex, 0) + 1
    print(f"  executor分布 (top 10):")
    for ex, cnt in sorted(exe_count.items(), key=lambda x:-x[1])[:10]:
        mark = "★算法组" if ex in ALGO_MEMBER_IDS else ""
        print(f"    {ex}: {cnt}条 {mark}")

if __name__ == "__main__":
    for name, pid, sfid in ALGO_PROJECTS:
        deep_inspect(name, pid, sfid)
