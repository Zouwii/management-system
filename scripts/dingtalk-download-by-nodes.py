#!/usr/bin/env python3
"""钉钉 MCP 按 node_id 批量下载 markdown

支持两种输入格式：

  1. 扁平模式: {"node_ids": ["id1", "id2", ...]}
     输出: {output_dir}/{node_id}.md

  2. 分级模式: {"nodes": [{"node_id": "...", "title": "...", "breadcrumb": "..."}, ...]}
     输出: {output_dir}/{breadcrumb层级}/{node_id}.md

用法:
  python3 dingtalk-download-by-nodes.py --input ids.json --output-dir /path/to/md [--workers 8]
"""

import argparse, json, os, re, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 强制无缓冲输出
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

MCP_URL = os.getenv("DINGTALK_KB_MCP_URL", "").strip()
MCP_DELAY = 0.15  # seconds between MCP calls to avoid rate limiting


def sanitize(name):
    """清理文件名中的非法字符"""
    return re.sub(r'[\\/:*?"<>|]', '-', name).strip()


def call_mcp(method, args, timeout=60):
    """调用钉钉 MCP 工具"""
    payload = {
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": method, "arguments": args},
    }
    try:
        r = subprocess.run(
            ["curl", "-s", "-X", "POST", MCP_URL,
             "-H", "Content-Type: application/json",
             "-H", "Accept: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=timeout,
        )
        return json.loads(r.stdout)
    except Exception as e:
        return {"error": str(e)}


def resolve_output_dir(base_dir, breadcrumb):
    """根据 breadcrumb 解析输出子目录

    breadcrumb 格式: "本体开发部 / 1. 工作规划 / 子目录"
    返回: base_dir/本体开发部/1. 工作规划/子目录/
    """
    parts = [sanitize(p) for p in breadcrumb.split(" / ") if p.strip()]
    d = Path(base_dir)
    for p in parts:
        d = d / p
    return d


def download_one(node_id, output_dir):
    """下载单个文档，返回 (node_id, output_dir, status, info)"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"{node_id}.md"
    json_path = output_dir / f"{node_id}.json"

    # 已存在则跳过
    if md_path.exists() and json_path.exists():
        return (node_id, str(output_dir), "skipped", None)

    try:
        result = call_mcp("get_document_content", {"nodeId": node_id})
        text = result.get("result", {}).get("content", [{}])[0].get("text", "{}")
        doc = json.loads(text)

        if not doc.get("success"):
            return (node_id, str(output_dir), "failed", doc.get("errorMsg", "unknown"))

        title = doc.get("title", "")
        markdown = doc.get("markdown", "")

        # 保存 markdown
        md_path.write_text(markdown, encoding="utf-8")
        # 保存 MCP 原始响应
        json_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

        return (node_id, str(output_dir), "ok", title)

    except Exception as e:
        return (node_id, str(output_dir), "failed", str(e))


def main():
    if not MCP_URL:
        print("❌ 缺少环境变量 DINGTALK_KB_MCP_URL", flush=True)
        sys.exit(2)

    parser = argparse.ArgumentParser(description="钉钉 MCP 按 node_id 批量下载 markdown")
    parser.add_argument("--input", "-i", required=True,
                        help='JSON 文件，支持两种格式:\n'
                             '  扁平: {"node_ids": ["id1", ...]}\n'
                             '  分级: {"nodes": [{"node_id":"...","title":"...","breadcrumb":"..."}, ...]}')
    parser.add_argument("--output-dir", "-o", required=True, help="输出根目录")
    parser.add_argument("--workers", "-w", type=int, default=8, help="并发数 (默认 8)")
    args = parser.parse_args()

    # 读取输入
    input_data = json.loads(Path(args.input).read_text(encoding="utf-8"))

    # 解析任务列表: [(node_id, output_subdir), ...]
    tasks = []
    nodes = input_data.get("nodes")
    node_ids = input_data.get("node_ids")

    if nodes:
        # 分级模式
        for n in nodes:
            nid = n.get("node_id", "")
            bc = n.get("breadcrumb", "")
            if nid:
                sub_dir = resolve_output_dir(args.output_dir, bc) if bc else args.output_dir
                tasks.append((nid, sub_dir))
    elif node_ids:
        # 扁平模式
        for nid in node_ids:
            tasks.append((nid, args.output_dir))
    else:
        print("❌ 输入文件需要 node_ids 或 nodes 字段", flush=True)
        sys.exit(1)

    if not tasks:
        print("❌ 没有待下载的文档", flush=True)
        sys.exit(1)

    output_root = Path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    print(f"📥 下载 {len(tasks)} 个文档 → {output_root}")
    print(f"🧵 并发: {args.workers}")
    if nodes:
        print(f"📂 分级模式: 按 breadcrumb 建目录")
    else:
        print(f"📂 扁平模式")
    print()

    stats = {"ok": 0, "skipped": 0, "failed": 0}
    lock = threading.Lock()
    completed = 0
    total = len(tasks)

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {}
        for nid, sub_dir in tasks:
            f = executor.submit(download_one, nid, sub_dir)
            futures[f] = nid
            time.sleep(MCP_DELAY)  # 错开请求

        for f in as_completed(futures):
            nid, sub_dir, status, info = f.result()
            completed += 1
            with lock:
                stats[status] = stats.get(status, 0) + 1

            rel = str(Path(sub_dir).relative_to(output_root)) if sub_dir != str(output_root) else "."
            if status == "ok":
                print(f"  ✅ [{completed}/{total}] {rel}/{nid}.md — {info or ''}", flush=True)
            elif status == "skipped":
                print(f"  ⏭ [{completed}/{total}] {rel}/{nid}.md (已存在)", flush=True)
            else:
                print(f"  ❌ [{completed}/{total}] {rel}/{nid}.md — {info or 'unknown error'}", flush=True)

    print()
    print(f"{'='*60}")
    print(f"📊 完成: {stats['ok']} 成功, {stats.get('skipped', 0)} 跳过, {stats['failed']} 失败")
    print(f"📂 输出: {output_root}")

    # 输出结果摘要
    summary_path = output_root / "_download_summary.json"
    summary = {
        "total": total,
        "ok": stats["ok"],
        "skipped": stats.get("skipped", 0),
        "failed": stats["failed"],
        "output_dir": str(output_root),
        "mode": "hierarchical" if nodes else "flat",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📋 摘要: {summary_path}")


if __name__ == "__main__":
    main()
