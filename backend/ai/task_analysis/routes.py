"""步骤1、2、3: AI 任务分析栏端点."""

from __future__ import annotations

import time

from flask import request, session


def _log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[task-analysis {ts}] {msg}", flush=True)


def _extract_keywords_from_tasks(tasks: list) -> str:
    """用 LLM 从任务列表中提取搜索关键词."""
    import json
    from pathlib import Path
    import requests

    titles = [str(t.get("title", "")).strip() for t in tasks if str(t.get("title", "")).strip()]
    if not titles:
        return ""

    skill_path = Path(__file__).resolve().parent.parent / "skills" / "1-1_keyword_extract" / "SKILL.md"
    skill_text = skill_path.read_text(encoding="utf-8")
    if skill_text.startswith("---"):
        end = skill_text.find("---", 3)
        if end != -1:
            skill_text = skill_text[end + 3:]
    skill_text = skill_text.strip()

    task_text = "\n".join(f"- {t}" for t in titles[:30])

    config_path = Path(__file__).resolve().parent.parent / "config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    base_url = str(cfg.get("base_url", "")).strip().rstrip("/")
    api_key = str(cfg.get("api_key", "")).strip()

    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={
                "model": "deepseek-v4-pro",
                "messages": [
                    {"role": "system", "content": skill_text},
                    {"role": "user", "content": f"从以下任务提取搜索关键词：\n{task_text}"},
                ],
                "temperature": 0.1,
                "max_tokens": 200,
            },
            timeout=30,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        keywords = msg.get("content", "").strip()
        if not keywords:
            keywords = msg.get("reasoning_content", "").strip()
        _log(f"LLM keywords: {keywords[:120]}")
        return keywords
    except Exception as e:
        _log(f"LLM keyword extract failed: {e}")
        return " ".join(titles[:6])


def register(bp, ok, fail):

    # ── 步骤1: 拉取任务数据 ────────────────────────────────────

    @bp.route("/ai/task-analysis/fetch-tasks", methods=["POST"])
    def ai_task_analysis_fetch_tasks():
        body = request.get_json(silent=True) or {}
        quarter = str(body.get("quarter") or "").strip()
        owner_key = str(body.get("owner_key") or "").strip() or None

        if not owner_key:
            auth_user = session.get("auth_user") or {}
            owner_key = str(auth_user.get("user_id") or "").strip() or None

        from ai.task_analysis.data import fetch_tasks
        try:
            t0 = time.time()
            result = fetch_tasks(quarter=quarter, owner_key=owner_key)
            elapsed = round(time.time() - t0, 1)
            s = result.get("stats", {})
            _log(f"step1 fetch-tasks: {s.get('total_tasks', 0)} tasks, {s.get('quarter_work_hour', 0)}d planned, {elapsed}s")
            return ok(result)
        except Exception as e:
            _log(f"step1 FAILED: {e}")
            return fail(str(e), code=500)

    # ── 步骤2: 知识库检索 ──────────────────────────────────────

    @bp.route("/ai/task-analysis/search-kb", methods=["POST"])
    def ai_task_analysis_search_kb():
        body = request.get_json(silent=True) or {}
        keywords = str(body.get("keywords") or "").strip()
        top_k = max(1, min(50, int(body.get("top_k") or 20)))
        tasks = body.get("tasks") or []
        do_generate = bool(body.get("generate")) and not keywords

        if do_generate and tasks:
            keywords = _extract_keywords_from_tasks(tasks)

        if not keywords:
            return fail("missing keywords", code=400)

        from ai.task_analysis.retrieval import search_kb
        try:
            t0 = time.time()
            result = search_kb(keywords, top_k=top_k)
            elapsed = round(time.time() - t0, 1)
            chunks = result.get("chunks", [])
            _log(f"step2 search-kb: '{keywords[:60]}...' → {len(chunks)} chunks, {elapsed}s")
            return ok(result)
        except Exception as e:
            _log(f"step2 FAILED: {e}")
            return fail(str(e), code=500)

    # ── 步骤3: 生成分析报告 ──────────────────────────────────────

    @bp.route("/ai/task-analysis/generate-report", methods=["POST"])
    def ai_task_analysis_generate_report():
        body = request.get_json(silent=True) or {}
        tasks = body.get("tasks") or []
        stats = body.get("stats") or {}
        chunks = body.get("chunks") or []

        if not tasks or not stats:
            return fail("missing tasks or stats from step 1", code=400)

        from ai.task_analysis.analysis import generate_report
        try:
            t0 = time.time()
            report = generate_report(tasks, stats, chunks)
            elapsed = round(time.time() - t0, 1)
            if "error" in report:
                _log(f"step3 generate-report: FAILED {report['error'][:80]}, {elapsed}s")
                return fail(report["error"], code=502, data=report)
            ok_modules = [k for k, v in report.items() if isinstance(v, dict) and "error" not in v]
            _log(f"step3 generate-report: {len(ok_modules)}/6 modules OK, {elapsed}s")
            return ok(report)
        except Exception as e:
            _log(f"step3 FAILED: {e}")
            return fail(str(e), code=500)
