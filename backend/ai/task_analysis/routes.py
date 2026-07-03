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
            if not tasks:
                _log("step2 search-kb: empty tasks, returning empty chunks")
                return ok({"chunks": [], "search_query": ""})
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
            if not tasks:
                _log("step3 generate-report: empty tasks, returning placeholder")
                return ok({
                    "requirement_radar": {"keywords": []},
                    "autonomous_suggestions": {"suggestions": []},
                    "capability_suggestions": {"suggestions": []},
                    "task_risk_analysis": {
                        "detail": "当前季度暂未查询到任务数据，请先创建 TB 任务单。点击下方「AI创建任务单」面板，使用 AI 辅助创建本季度的工作任务。",
                    },
                })
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

    # ── 绩效达标分析 ──────────────────────────────────────────

    @bp.route("/ai/task-analysis/performance-report", methods=["POST"])
    def ai_task_analysis_performance_report():
        body = request.get_json(silent=True) or {}
        owner_key = str(body.get("owner_key") or "").strip() or None

        if not owner_key:
            auth_user = session.get("auth_user") or {}
            owner_key = str(auth_user.get("user_id") or "").strip() or None

        if not owner_key:
            return fail("missing owner_key", code=400)

        from performance.service import performance_history_service
        from ai.task_analysis.data import fetch_tasks
        from ai.task_analysis.performance_analysis import generate_performance_report

        try:
            t0 = time.time()

            # 1. 拉取绩效历史，提取上季结余
            perf_out = performance_history_service({"target": owner_key})
            prev_carry = 0.0
            if perf_out.get("success"):
                history = (perf_out.get("data") or {}).get("history") or []
                if history:
                    prev_carry = float(history[-1].get("carryScore", 0) or 0)
            _log(f"perf-report: prev_carry={prev_carry:.3f}")

            # 2. 拉取当前季度排单
            task_out = fetch_tasks(owner_key=owner_key)
            tasks = task_out.get("tasks", [])
            stats = task_out.get("stats", {})
            _log(f"perf-report: {stats.get('total_tasks', 0)} tasks, {stats.get('quarter_work_hour', 0)}d planned")

            # 3. LLM 分析
            report = generate_performance_report(prev_carry, tasks, stats)
            elapsed = round(time.time() - t0, 1)

            if "error" in report:
                _log(f"performance-report: FAILED {report['error'][:80]}, {elapsed}s")
                return fail(report["error"], code=502, data=report)

            ok_modules = [k for k, v in report.items() if isinstance(v, dict) and "error" not in v]
            _log(f"performance-report: {len(ok_modules)}/2 modules OK, {elapsed}s")
            return ok(report)
        except Exception as e:
            _log(f"performance-report FAILED: {e}")
            return fail(str(e), code=500)

    # ── apply_suggestion: 应用分析建议，创建 TB 任务模板 ─────────

    @bp.route("/ai/task-analysis/apply-suggestion", methods=["POST"])
    def ai_task_analysis_apply_suggestion():
        body = request.get_json(silent=True) or {}
        suggestion_type = str(body.get("suggestion_type") or "").strip()
        suggestion = body.get("suggestion") or {}

        if suggestion_type not in ("autonomous", "capability", "performance"):
            return fail("invalid suggestion_type, must be 'autonomous', 'capability', or 'performance'", code=400)

        template = suggestion.get("task_template") or {}
        title = str(template.get("title") or "").strip()
        requirement_desc = str(template.get("requirement_desc") or "").strip()

        # 兼容两种格式：outputs（数组）和 output（字符串）
        outputs_arr = template.get("outputs")
        if isinstance(outputs_arr, list) and outputs_arr:
            output = "\n".join(str(o) for o in outputs_arr)
        else:
            output = str(template.get("output") or "").strip()

        if not title:
            return fail("task_template.title is required", code=400)

        owner_key = str(body.get("owner_key") or "").strip()
        if not owner_key:
            auth_user = session.get("auth_user") or {}
            owner_key = str(auth_user.get("user_id") or "").strip()

        _log(f"apply_suggestion: type={suggestion_type} title={title[:60]} owner={owner_key}")

        return ok({
            "accepted": True,
            "suggestion_type": suggestion_type,
            "template": {
                "title": title,
                "requirement_desc": requirement_desc,
                "output": output,
            },
            "owner_key": owner_key,
        })
