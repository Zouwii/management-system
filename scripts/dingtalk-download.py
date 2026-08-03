#!/usr/bin/env python3
"""钉钉知识库多线程递归下载脚本
用法: python3 dingtalk-download.py <workspaceId> [folderId] [输出目录] [并发数]
示例: python3 dingtalk-download.py 1oam4Sk7BMLXxn8K
      python3 dingtalk-download.py 1oam4Sk7BMLXxn8K dQPGYqjpJYgoNr9ZCxN9DLzNWakx1Z5N /home/jz/zhr/markdown 8
"""

import json, os, re, subprocess, sys, time, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# 强制无缓冲输出，确保日志实时写入
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

MCP_URL = os.getenv("DINGTALK_KB_MCP_URL", "").strip()
DL_DELAY = 0.3  # seconds between list_nodes calls

class DingTalkDownloader:
    def __init__(self, base_dir, max_workers=8):
        self.base_dir = Path(base_dir)
        self.max_workers = max_workers
        self.stats = {"docs": 0, "imgs": 0, "errors": 0, "skipped": 0}
        self.lock = threading.Lock()
        self.img_urls = set()  # deduplicate
        self.img_lock = threading.Lock()

    def _mcp(self, method, args):
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": method, "arguments": args}}
        r = subprocess.run(["curl", "-s", "-X", "POST", MCP_URL,
            "-H", "Content-Type: application/json", "-H", "Accept: application/json",
            "-d", json.dumps(payload)], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout)

    def _sanitize(self, name):
        return re.sub(r'[\\/:*?"<>|]', '-', name).strip()

    # ===== Phase 1: 收集目录树 =====

    def list_folder(self, folder_id=None, workspace_id=None, page_token=None):
        args = {"pageSize": 50}
        if folder_id:
            args["folderId"] = folder_id
        if workspace_id:
            args["workspaceId"] = workspace_id
        if page_token:
            args["pageToken"] = page_token
        result = self._mcp("list_nodes", args)
        text = result["result"]["content"][0]["text"]
        return json.loads(text)

    def collect_nodes(self, folder_id=None, workspace_id=None, rel_path="", max_depth=10):
        """单线程递归收集所有节点，返回 [(node, save_dir, parent_name)]"""
        if max_depth <= 0:
            return []

        all_nodes = []
        page_token = None
        while True:
            nodes = self.list_folder(folder_id=folder_id, workspace_id=workspace_id, page_token=page_token)
            all_nodes.extend(nodes.get("nodes", []))
            if not nodes.get("hasMore"):
                break
            page_token = nodes.get("nextPageToken")
            time.sleep(DL_DELAY)

        print(f"  📂 {rel_path or '/'} ({len(all_nodes)} 项)", flush=True)

        tasks = []  # (node_info, save_dir)
        for node in all_nodes:
            name = node["name"]
            node_id = node["nodeId"]
            node_type = node.get("nodeType", "file")
            ext = node.get("extension", "")
            has_children = node.get("hasChildren", False)
            save_dir = self.base_dir / rel_path

            if node_type == "folder":
                if has_children:
                    sub_path = os.path.join(rel_path, self._sanitize(name))
                    tasks.extend(self.collect_nodes(folder_id=node_id, rel_path=sub_path, max_depth=max_depth - 1))
                continue

            if ext == "adoc":
                tasks.append({"node_id": node_id, "save_dir": save_dir, "name": name, "ext": ext})
                if has_children:
                    sub_path = os.path.join(rel_path, self._sanitize(name))
                    tasks.extend(self.collect_nodes(folder_id=node_id, rel_path=sub_path, max_depth=max_depth - 1))
            elif ext == "axls":
                tasks.append({"node_id": node_id, "save_dir": save_dir, "name": name, "ext": ext})
            else:
                with self.lock:
                    self.stats["skipped"] += 1
                print(f"  ⏭ 跳过 {name} (ext={ext})")

        return tasks

    # ===== Phase 2: 多线程下载 =====

    def download_img(self, url, save_dir):
        url = url.rstrip(' "')
        parsed = urlparse(url)
        name = os.path.basename(parsed.path)
        if not name or not any(name.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp']):
            name = f"img_{hash(url) & 0xffff}.png"

        save_path = save_dir / name
        if save_path.exists():
            return name

        try:
            r = subprocess.run(["curl", "-s", "-o", str(save_path), "-w", "%{http_code}", url],
                               capture_output=True, text=True, timeout=30)
            if r.stdout == "200":
                with self.lock:
                    self.stats["imgs"] += 1
                return name
            return None
        except Exception:
            return None

    def download_adoc(self, task):
        """下载单个 adoc 文档 + 图片"""
        node_id = task["node_id"]
        save_dir = task["save_dir"]
        name_hint = task["name"]

        try:
            result = self._mcp("get_document_content", {"nodeId": node_id})
            text = result["result"]["content"][0]["text"]
            doc = json.loads(text)

            if not doc.get("success"):
                print(f"  ⚠ {name_hint}: {doc.get('errorMsg', 'unknown')}")
                with self.lock:
                    self.stats["errors"] += 1
                return

            title = self._sanitize(name_hint or doc.get("title", "untitled"))
            md = doc.get("markdown", "")

            save_dir.mkdir(parents=True, exist_ok=True)
            md_path = save_dir / f"{title}.md"
            with open(md_path, 'w') as f:
                f.write(md)

            with self.lock:
                self.stats["docs"] += 1

            # Extract OSS images
            img_urls = list(set(
                re.findall(r'https://alidocs2\.oss[^\s)]+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:\?[^\s)]*)?', md, re.IGNORECASE)
                + re.findall(r'https://alidocs2\.oss[^\s)]+', md)
            ))

            imgs_dir = save_dir / "images"
            dl_count = 0
            for url in img_urls:
                with self.img_lock:
                    if url in self.img_urls:
                        continue
                    self.img_urls.add(url)
                imgs_dir.mkdir(exist_ok=True)
                self.download_img(url, imgs_dir)
                dl_count += 1

            img_tag = f" 📷{dl_count}" if dl_count else ""
            print(f"  ✅ {title}.md ({len(md)} 字符){img_tag}")

        except Exception as e:
            print(f"  ❌ {name_hint}: {e}")
            with self.lock:
                self.stats["errors"] += 1

    def download_axls(self, task):
        """下载 axls 表格"""
        try:
            result = self._mcp("submit_export_job", {
                "nodeId": task["node_id"],
                "exportFormat": "markdown"
            })
            text = result["result"]["content"][0]["text"]
            job = json.loads(text)

            if not job.get("success"):
                print(f"  ⚠ {task['name']}: 导出不支持 (axls)")
                with self.lock:
                    self.stats["skipped"] += 1
                return

            task_id = job.get("taskId")
            if not task_id:
                return

            for _ in range(10):
                time.sleep(2)
                result = self._mcp("query_export_job", {"taskId": task_id})
                text = result["result"]["content"][0]["text"]
                q = json.loads(text)
                if q.get("status") == "success":
                    download_url = q.get("downloadUrl")
                    if download_url:
                        title = self._sanitize(task["name"])
                        task["save_dir"].mkdir(parents=True, exist_ok=True)
                        save_path = task["save_dir"] / f"{title}.md"
                        r = subprocess.run(["curl", "-s", "-o", str(save_path), "-w", "%{http_code}", download_url],
                                           capture_output=True, text=True, timeout=30)
                        if r.stdout == "200":
                            size = save_path.stat().st_size
                            with self.lock:
                                self.stats["docs"] += 1
                            print(f"  ✅ {title}.md ({size} bytes, from axls)")
                        else:
                            print(f"  ⚠ {title}: download failed [{r.stdout}]")
                            with self.lock:
                                self.stats["errors"] += 1
                    return
                elif q.get("status") == "error":
                    print(f"  ⚠ {task['name']}: 导出失败")
                    with self.lock:
                        self.stats["errors"] += 1
                    return

        except Exception as e:
            print(f"  ❌ {task['name']}: {e}")
            with self.lock:
                self.stats["errors"] += 1

    def download_worker(self, task):
        if task["ext"] == "adoc":
            self.download_adoc(task)
        elif task["ext"] == "axls":
            self.download_axls(task)

    # ===== Main =====

    def run(self, workspace_id, folder_id=None, rel_path=""):
        start = f"workspace={workspace_id}" + (f" folder={folder_id}" if folder_id else "")
        print(f"🚀 开始下载: {start}")
        print(f"📂 输出: {self.base_dir / rel_path}")
        print(f"🧵 并发: {self.max_workers}")
        print()

        # Phase 1: 收集所有节点
        print("📋 Phase 1: 收集目录树...")
        if folder_id:
            tasks = self.collect_nodes(folder_id=folder_id, rel_path=rel_path)
        else:
            tasks = self.collect_nodes(workspace_id=workspace_id, rel_path=rel_path)

        total = len(tasks)
        print(f"   共 {total} 个文档待下载")
        print()

        # Phase 2: 多线程下载
        print(f"📥 Phase 2: 多线程下载 ({self.max_workers} threads)...")
        completed = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.download_worker, t): t for t in tasks}
            for _ in as_completed(futures):
                completed += 1
                if completed % 20 == 0:
                    print(f"   进度: {completed}/{total}")

        print(f"\n{'='*60}")
        print(f"📊 完成: {self.stats['docs']} 文档, {self.stats['imgs']} 图片, "
              f"{self.stats['skipped']} 跳过, {self.stats['errors']} 错误")


if __name__ == "__main__":
    if not MCP_URL:
        print("缺少环境变量 DINGTALK_KB_MCP_URL")
        sys.exit(2)

    if len(sys.argv) < 2:
        print("用法: python3 dingtalk-download.py <workspaceId> [folderId] [输出目录] [并发数]")
        print("示例: python3 dingtalk-download.py 1oam4Sk7BMLXxn8K")
        print("      python3 dingtalk-download.py 1oam4Sk7BMLXxn8K dQPGYqjpJYgoNr9ZCxN9DLzNWakx1Z5N /home/jz/zhr/markdown 8")
        sys.exit(1)

    ws_id = sys.argv[1]
    folder_id = sys.argv[2] if len(sys.argv) > 2 else None
    out_dir = sys.argv[3] if len(sys.argv) > 3 else "docs/markdown"
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 8

    dl = DingTalkDownloader(out_dir, max_workers=workers)
    dl.run(ws_id, folder_id)
