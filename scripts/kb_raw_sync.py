#!/usr/bin/env python3
"""
裸调钉钉 API 拉取知识库 — 不经过 Flask，不写 api_call_logs。

API 用量会在终端实时显示 + 最终汇总。

用法:
  python3 kb_raw_sync.py --estimate-only      # 仅遍历目录树统计（不下载正文）
  python3 kb_raw_sync.py                      # 全量同步到 SQLite
  python3 kb_raw_sync.py --estimate-only --dump-sql  # 先估算，确定体量后再全量
  python3 kb_raw_sync.py --ws xPar2SAKPb4KZbaV       # 只拉单个 workspace

输出:
  - 终端: 实时进度 + API 调用明细
  - kb_storage_raw.db: SQLite 数据库（kb_nodes + kb_documents）
  - kb_storage_raw.sql: --dump-sql 时导出

依赖: pip install pymysql (读写 MySQL 用 union_id)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import requests
import pymysql

# ── 路径 ──────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent  # scripts/ → management-system/
CONFIG_JSON = BASE_DIR / "backend" / "base" / "config.json"
WORKSPACES_JSON = BASE_DIR / "backend" / "base" / "kb_workspaces.json"

DINGTALK_API = "https://api.dingtalk.com"
DINGTALK_OAPI = "https://oapi.dingtalk.com"

MYSQL_CONF = {
    "host": "127.0.0.1", "port": 3306,
    "user": "root", "password": "123456",
    "database": "benti_management",
}

TIMEOUT = 30
BATCH_SIZE = 100

# ── API 用量记录 ──────────────────────────────────────────────────

class ApiMeter:
    """记录每次 API 调用的 endpoint + 状态码 + 耗时，不入任何数据库表"""
    def __init__(self):
        self.calls: List[dict] = []       # [{ep, status, ms}]
        self.by_endpoint: Dict[str, int] = {}
        self.errors: List[str] = []

    def record(self, endpoint: str, status: int, ms: int):
        self.calls.append({"ep": endpoint, "status": status, "ms": ms})
        self.by_endpoint[endpoint] = self.by_endpoint.get(endpoint, 0) + 1

    def record_error(self, endpoint: str, err: str):
        self.errors.append(f"[{endpoint}] {err}")

    def total(self) -> int:
        return len(self.calls)

    def report(self) -> str:
        lines = []
        lines.append("─" * 50)
        lines.append("  API 用量报告")
        lines.append("─" * 50)
        lines.append(f"  总调用次数: {self.total()}")
        if self.errors:
            lines.append(f"  失败次数:   {len(self.errors)}")
        lines.append("")
        lines.append("  按接口分布:")
        for ep, cnt in sorted(self.by_endpoint.items(), key=lambda x: -x[1]):
            # 计算平均耗时
            ep_calls = [c for c in self.calls if c["ep"] == ep]
            avg_ms = sum(c["ms"] for c in ep_calls) / len(ep_calls) if ep_calls else 0
            lines.append(f"    {cnt:>5} 次  avg {avg_ms:>6.0f}ms  {ep}")
        lines.append("")
        # 预估费用（按钉钉 API 免费额度看）
        lines.append("  💡 list_nodes = 遍历目录，get_document_blocks = 下载正文")
        lines.append(f"  💡 token 调用不计入 KB 同步配额")
        lines.append("─" * 50)
        return "\n".join(lines)

meter = ApiMeter()

# ── Token ─────────────────────────────────────────────────────────

def get_access_token():
    cfg = json.loads(CONFIG_JSON.read_text()) if CONFIG_JSON.exists() else {}
    now = int(time.time())
    cached = cfg.get("access_token", "")
    expire_at = cfg.get("token_expire_at", 0)
    if cached and int(expire_at) > now + 60:
        return cached

    t0 = time.time()
    resp = requests.get(f"{DINGTALK_OAPI}/gettoken",
                        params={"appkey": cfg["appkey"], "appsecret": cfg["appsecret"]},
                        timeout=TIMEOUT)
    meter.record("dingtalk/gettoken", resp.status_code, int((time.time()-t0)*1000))
    data = resp.json()
    if data.get("errcode", -1) != 0:
        raise RuntimeError(f"gettoken 失败: {data}")
    cfg["access_token"] = data["access_token"]
    cfg["token_expire_at"] = now + int(data.get("expires_in", 7200))
    CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    return data["access_token"]

def get_union_id():
    conn = pymysql.connect(**MYSQL_CONF)
    try:
        with conn.cursor() as c:
            c.execute("SELECT union_id FROM user_character WHERE union_id IS NOT NULL AND union_id != '' LIMIT 1")
            row = c.fetchone()
            if row: return row[0]
    finally:
        conn.close()
    raise RuntimeError("找不到 union_id")

# ── 钉钉 API 客户端 ──────────────────────────────────────────────

class RawKB:
    def __init__(self, token, union_id):
        self.h = {"x-acs-dingtalk-access-token": token, "Content-Type": "application/json"}
        self.uid = union_id

    def _get(self, path, params=None):
        url = f"{DINGTALK_API}{path}"
        p = dict(params or {})
        t0 = time.time()
        try:
            resp = requests.get(url, headers=self.h, params=p, timeout=TIMEOUT)
            ms = int((time.time() - t0) * 1000)
            meter.record(path, resp.status_code, ms)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            ok = 200 <= resp.status_code < 300
            if not ok:
                meter.record_error(path, f"HTTP {resp.status_code}: {str(data)[:200]}")
            return {"ok": ok, "data": data, "status": resp.status_code}
        except requests.RequestException as e:
            meter.record_error(path, str(e))
            return {"ok": False, "error": str(e), "data": {}}

    def list_workspaces(self):
        r = self._get("/v2.0/wiki/workspaces", {"operatorId": self.uid})
        if not r["ok"]: return r
        ws = r.get("data", {}).get("workspaces") or []
        return {"ok": True, "data": [{"workspaceId": w.get("workspaceId",""),
                "name": w.get("name",""), "rootNodeId": w.get("rootNodeId","")} for w in ws]}

    def list_nodes(self, workspace_id, parent_id=""):
        p = {"workspaceId": workspace_id, "operatorId": self.uid}
        if parent_id: p["parentNodeId"] = parent_id
        r = self._get("/v2.0/wiki/nodes", p)
        if not r["ok"]: return r
        nodes = r.get("data", {}).get("nodes") or []
        items = []
        for n in nodes:
            items.append({"nodeId": n.get("nodeId",""), "name": n.get("name",""),
                "type": n.get("type","FILE").upper(), "category": n.get("category",""),
                "hasChildren": n.get("hasChildren",False), "modifiedTime": n.get("modifiedTime",""),
                "workspaceId": workspace_id})
        return {"ok": True, "data": items}

    def get_document_blocks(self, node_id):
        r = self._get(f"/v1.0/doc/suites/documents/{node_id}/blocks", {"operatorId": self.uid})
        if not r["ok"]: return r
        blocks = r.get("data", {}).get("result", {}).get("data") or []
        return {"ok": True, "data": blocks}

# ── 文档解析 ──────────────────────────────────────────────────────

def blocks_to_md(blocks):
    lines = []
    for b in blocks:
        bt = b.get("blockType", 0)
        texts = b.get("texts", []) or b.get("paragraph", {}).get("texts", [])
        if not texts: continue
        raw = "".join(t.get("text","") for t in texts)
        style = next((t.get("style",{}) for t in texts if t.get("style")), {})
        if bt in (2,3,4,5,6):
            lines.append(f"{'#'*(bt-1)} {raw}\n")
        elif bt == 7:
            tid = b.get("id",""); mid = tid.get("mid","") if isinstance(tid,dict) else str(tid)
            d = int(mid.count(".")) if "." in str(mid) else 0
            lines.append(f"{'  '*d}- {raw}\n")
        elif bt == 8:
            tid = b.get("id",""); mid = tid.get("mid","") if isinstance(tid,dict) else str(tid)
            d = int(mid.count(".")) if "." in str(mid) else 0
            lines.append(f"{'  '*d}1. {raw}\n")
        elif bt in (9,10):
            lines.append(f"- [{'x' if bt==10 else ' '}] {raw}\n")
        elif bt == 11:
            lines.append("---\n")
        elif bt == 12:
            lang = style.get("language","")
            lines.append(f"```{lang}\n{raw}\n```\n")
        elif bt == 13:
            lines.append(f"> {raw}\n")
        elif bt == 14:
            emoji = style.get("emoji","")
            lines.append(f"> {emoji} **{raw}**\n")
        elif bt == 15:
            for row in b.get("cells",[]):
                rt = " | ".join("".join(t.get("text","") for t in c.get("texts",[])) for c in row)
                lines.append(f"| {rt} |\n")
        else:
            lines.append(f"{raw}\n\n")
    return "".join(lines)

# ── SQLite 存储 ───────────────────────────────────────────────────

SQL_NODES = """
CREATE TABLE IF NOT EXISTS kb_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL UNIQUE,
    workspace_id TEXT NOT NULL, parent_id TEXT DEFAULT '', name TEXT NOT NULL,
    node_type TEXT NOT NULL, category TEXT DEFAULT '', has_children INTEGER DEFAULT 0,
    depth INTEGER DEFAULT 0, breadcrumb TEXT DEFAULT '',
    remote_modified_at TEXT, sync_status TEXT DEFAULT 'synced', sync_error TEXT DEFAULT '',
    synced_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS i_kn_ws ON kb_nodes(workspace_id);
CREATE INDEX IF NOT EXISTS i_kn_p ON kb_nodes(parent_id);"""

SQL_DOCS = """
CREATE TABLE IF NOT EXISTS kb_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, node_id TEXT NOT NULL UNIQUE,
    workspace_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT DEFAULT '',
    raw_json TEXT DEFAULT '', fetch_status TEXT DEFAULT 'success', fail_reason TEXT DEFAULT '',
    synced_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS i_kd_ws ON kb_documents(workspace_id);"""

class KBStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
        self.db.executescript(SQL_NODES)
        self.db.executescript(SQL_DOCS)
        self.db.commit()
        self.nc = self.dc = 0

    def upsert_node(self, nid, ws, pid, name, ntype, cat, hc, depth, bc, rmt):
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("""INSERT INTO kb_nodes
            (node_id,workspace_id,parent_id,name,node_type,category,has_children,depth,breadcrumb,remote_modified_at,sync_status,synced_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,'synced',?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
            name=excluded.name,category=excluded.category,has_children=excluded.has_children,
            depth=excluded.depth,breadcrumb=excluded.breadcrumb,
            remote_modified_at=excluded.remote_modified_at,
            sync_status='synced',sync_error='',synced_at=excluded.synced_at,updated_at=excluded.updated_at""",
            (nid,ws,pid,name,ntype,cat,1 if hc else 0,depth,bc,rmt,now,now,now))
        self.nc += 1
        if self.nc % BATCH_SIZE == 0: self.db.commit()

    def insert_doc(self, nid, ws, title, content, raw):
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("""INSERT INTO kb_documents
            (node_id,workspace_id,title,content,raw_json,fetch_status,synced_at,created_at,updated_at)
            VALUES (?,?,?,?,?,'success',?,?,?)
            ON CONFLICT(node_id) DO UPDATE SET
            title=excluded.title,content=excluded.content,raw_json=excluded.raw_json,
            fetch_status='success',fail_reason='',synced_at=excluded.synced_at,updated_at=excluded.updated_at""",
            (nid,ws,title,content,raw,now,now,now))
        self.dc += 1
        if self.dc % BATCH_SIZE == 0: self.db.commit()

    def commit(self): self.db.commit()
    def close(self): self.db.commit(); self.db.close()

    def dump_sql(self, out):
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"-- kb_raw_sync dump {datetime.now().isoformat()}\n\n")
            for tbl in ("kb_nodes", "kb_documents"):
                rows = self.db.execute(f"SELECT * FROM {tbl}").fetchall()
                cols = [d[0] for d in self.db.execute(f"PRAGMA table_info({tbl})")]
                f.write(f"-- {tbl}: {len(rows)} rows\n")
                for row in rows:
                    vals = ",".join(f"'{str(v).replace(chr(39),chr(39)+chr(39))}'" if v is not None else "NULL" for v in row)
                    f.write(f"INSERT INTO {tbl} ({','.join(cols)}) VALUES ({vals});\n")
        print(f"  SQL dump → {out}")

# ── workspace 配置 ────────────────────────────────────────────────

def load_workspaces(priority=None):
    if not WORKSPACES_JSON.exists(): return []
    data = json.loads(WORKSPACES_JSON.read_text())
    out = []
    for name, e in data.get("kb_workspaces", {}).items():
        if not isinstance(e, dict) or not e.get("enabled"): continue
        ws_id = str(e.get("workspace_id","")).strip()
        if not ws_id: continue
        p = int(e.get("priority", 999))
        if priority is not None and p != priority: continue
        out.append({"name": name, "workspace_id": ws_id, "priority": p})
    out.sort(key=lambda x: x["priority"])
    return out

def parse_dt(ts):
    if not ts: return None
    try: return datetime.fromisoformat(str(ts).replace("Z","+00:00")).isoformat()
    except: return None

# ── 核心 ──────────────────────────────────────────────────────────

def sync_ws(client, store, ws_id, root_id, ws_name, est_only):
    fn = fd = sk = 0
    st = {"nodes":0,"files":0,"alidoc":0,"workbook":0,"folders":0}

    def walk(pid, bc, depth):
        nonlocal fn, fd, sk
        r = client.list_nodes(ws_id, pid)
        if not r["ok"]:
            fn += 1
            print(f"    [ERR] list_nodes pid={pid}: {r.get('error','?')}", flush=True)
            return
        for n in r["data"]:
            nid, ntype, name = n["nodeId"], n["type"], n["name"]
            cat = (n.get("category") or "").strip().upper()
            hc, rmt = n.get("hasChildren", False), n.get("modifiedTime", "")
            bc2 = f"{bc} / {name}" if bc else name
            store.upsert_node(nid, ws_id, pid, name, ntype, cat, hc, depth, bc2, parse_dt(rmt))
            st["nodes"] += 1
            if ntype == "FOLDER":
                st["folders"] += 1
                if hc: walk(nid, bc2, depth + 1)
            elif ntype == "FILE":
                st["files"] += 1
                if cat == "ALIDOC": st["alidoc"] += 1
                elif cat == "WORKBOOK": st["workbook"] += 1; sk += 1; continue
                else: sk += 1; continue
                if est_only: continue
                try:
                    br = client.get_document_blocks(nid)
                    if not br["ok"]:
                        fd += 1
                        print(f"    [ERR] blocks {nid} {name}: {br.get('error','?')}", flush=True)
                        continue
                    md = blocks_to_md(br["data"])
                    store.insert_doc(nid, ws_id, name, md, json.dumps(br, ensure_ascii=False))
                except Exception as e:
                    fd += 1
                    print(f"    [ERR] {nid} {name}: {e}", flush=True)

    store.upsert_node(root_id, ws_id, "", ws_name, "FOLDER", "", True, 0, ws_name, None)
    st["nodes"] += 1
    t0 = time.time()
    walk(root_id, ws_name, 1)
    store.commit()
    return {**st, "failed_nodes": fn, "failed_docs": fd, "skipped": sk,
            "elapsed": round(time.time()-t0, 1), "name": ws_name}

# ── main ──────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="裸调钉钉 API 拉取 KB（不入 api_call_logs）")
    ap.add_argument("--estimate-only", action="store_true", help="仅遍历统计，不下载正文")
    ap.add_argument("--priority", type=int, default=99, help="只拉该 priority 的 workspace（默认 99）")
    ap.add_argument("--db", default="kb_storage_raw.db", help="SQLite 路径（默认 kb_storage_raw.db）")
    ap.add_argument("--dump-sql", action="store_true", help="完成后导出 SQL dump")
    ap.add_argument("--ws", default="", help="只拉指定 workspace_id")
    ap.add_argument("--uid", default="", help="union_id（本地跑时可手动指定，跳过 MySQL 连接）")
    args = ap.parse_args()

    print("=" * 60)
    print(f"  裸调 KB 同步 | 模式: {'仅估算' if args.estimate_only else '全量同步'} | priority={args.priority}")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Token + union_id
    print("\n▶ 获取 token & union_id...", flush=True)
    token = get_access_token()
    if args.uid:
        uid = args.uid
        print(f"  uid (手动指定)", flush=True)
    else:
        try:
            uid = get_union_id()
        except Exception:
            print(f"  WARNING: MySQL 不可达，请用 --uid 手动指定 union_id")
            sys.exit(1)
    print(f"  token={token[:8]}...  union_id={uid[:8]}...", flush=True)

    client = RawKB(token, uid)

    # 加载 workspace
    wss = load_workspaces(args.priority)
    if args.ws:
        wss = [w for w in wss if w["workspace_id"] == args.ws]
    print(f"\n▶ 待同步 workspace: {len(wss)} 个")
    for w in wss:
        print(f"    [{w['priority']}] {w['name']}  ({w['workspace_id']})")

    # 获取 rootNodeId
    print("\n▶ 获取 rootNodeId...", flush=True)
    all_ws = client.list_workspaces()
    if not all_ws["ok"]:
        print(f"  ERROR: {all_ws}"); sys.exit(1)
    wmap = {w["workspaceId"]: w for w in all_ws["data"]}
    targets = []
    for w in wss:
        r = wmap.get(w["workspace_id"])
        if r and r.get("rootNodeId"):
            targets.append({"name": w["name"], "ws_id": w["workspace_id"], "root": r["rootNodeId"]})
            print(f"    ✓ {w['name']}")
        else:
            print(f"    ✗ {w['name']} 无权限或无 rootNodeId")

    if not targets:
        print("ERROR: 无可用 workspace"); sys.exit(1)

    # 同步
    print(f"\n▶ 开始遍历 {len(targets)} 个 workspace...\n", flush=True)
    store = KBStore(args.db)
    results = []
    t_total = time.time()

    for i, t in enumerate(targets):
        print(f"── [{i+1}/{len(targets)}] {t['name']} ──", flush=True)
        r = sync_ws(client, store, t["ws_id"], t["root"], t["name"], args.estimate_only)
        r["ws_id"] = t["ws_id"]
        results.append(r)
        print(f"  nodes={r['nodes']} files={r['files']} alidoc={r['alidoc']} "
              f"workbook={r['workbook']} failed=(n={r['failed_nodes']},d={r['failed_docs']}) "
              f"耗时={r['elapsed']}s\n", flush=True)

    elapsed = round(time.time() - t_total, 1)

    # ──── 汇总 ────
    tn = sum(r["nodes"] for r in results)
    tf = sum(r["files"] for r in results)
    ta = sum(r["alidoc"] for r in results)
    tw = sum(r["workbook"] for r in results)

    print("=" * 60)
    print("  数据汇总")
    print("=" * 60)
    print(f"  workspace:        {len(results)}")
    print(f"  总节点:           {tn}")
    print(f"  FILE 总数:        {tf}")
    print(f"  ALIDOC (已下载):  {ta}")
    print(f"  WORKBOOK (跳过):  {tw}")
    print(f"  总耗时:           {elapsed}s")
    print(f"  数据文件:         {os.path.abspath(args.db)}")
    print()
    print(meter.report())

    if args.dump_sql:
        store.dump_sql(args.db.replace(".db", ".sql"))

    store.close()

if __name__ == "__main__":
    main()
