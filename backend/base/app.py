import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import threading
import time as _time
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from flask import Flask, abort, send_from_directory
from flask_cors import CORS

from base.api import api_bp
from base.route_registry.dashboard import dashboard_bp
from base.db import SessionLocal, init_db
from base.db.config import env_bt

_VUE_DIR = Path(__file__).resolve().parent.parent / "static" / "react"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["SECRET_KEY"] = env_bt("SECRET_KEY", "replace-this-in-production")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = env_bt("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = str(env_bt("SESSION_COOKIE_SECURE", "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(seconds=int(env_bt("SESSION_EXPIRE_SECONDS", "86400")))

    cors_origins = env_bt("CORS_ORIGINS", "*")
    if cors_origins.strip() == "*":
        CORS(app, resources={r"/api/bt/*": {"origins": "*"}})
    else:
        origins = [x.strip() for x in cors_origins.split(",") if x.strip()]
        CORS(app, resources={r"/api/bt/*": {"origins": origins}}, supports_credentials=True)

    init_db()

    # Embedding model loading is expensive; keep app startup fast by default.
    # Set AI_PRELOAD_EMBEDDING=1 only on hosts that intentionally serve vector search.
    if str(os.getenv("AI_PRELOAD_EMBEDDING", "0")).strip().lower() in ("1", "true", "yes", "on"):
        try:
            from ai.knowledge.embedder import _load_model
            _load_model()
        except Exception:
            pass

    # 后台：根据 config 表里的自动计算设置，到点触发"更新数据"
    # 注意：用 daemon thread，且通过模块级标记避免重复启动。
    global _AUTO_CALC_THREAD_STARTED
    if not globals().get("_AUTO_CALC_THREAD_STARTED"):
        _AUTO_CALC_THREAD_STARTED = True

        def _auto_calc_loop():
            from base.config.service import (
                get_workhour_auto_calc_service,
                touch_last_update_time_service,
                get_last_update_time_service,
            )

            from base.api_monitor import BJ_TZ

            while True:
                try:
                    cfg = get_workhour_auto_calc_service() or {}
                    auto_time = str(cfg.get("auto_calc_time") or "").strip()
                    parts = auto_time.split(":") if auto_time else []
                    enabled = bool(cfg.get("auto_calc_enabled"))
                    hh, mm = (int(parts[0]), int(parts[1])) if len(parts) == 2 else (None, None)

                    if not enabled or hh is None:
                        _time.sleep(60)
                        continue

                    now = datetime.now(BJ_TZ)
                    today = now.strftime("%Y-%m-%d")

                    # 今天是否已触发
                    lu = get_last_update_time_service() or {}
                    last = lu.get("last_update_time") or ""
                    done_today = False
                    if last:
                        try:
                            if datetime.fromisoformat(last).astimezone().strftime("%Y-%m-%d") == today:
                                done_today = True
                        except Exception:
                            pass

                    # 算下次触发时间（未触发→今天的目标时刻, 已触发→明天的）
                    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    if target <= now:
                        target += timedelta(days=1)

                    # sleep 到触发时刻
                    wait = (target - now).total_seconds()
                    if wait > 0:
                        _time.sleep(wait)

                    # 再次读配置确认没变 + 防同天重复
                    cfg2 = get_workhour_auto_calc_service() or {}
                    lu2 = get_last_update_time_service() or {}
                    last2 = lu2.get("last_update_time") or ""
                    done2 = False
                    if last2:
                        try:
                            if datetime.fromisoformat(last2).astimezone().strftime("%Y-%m-%d") == datetime.now(BJ_TZ).strftime("%Y-%m-%d"):
                                done2 = True
                        except Exception:
                            pass

                    if cfg2.get("auto_calc_enabled") and not done2:
                        touch_last_update_time_service()

                    _time.sleep(1)  # 避免同一秒重复触发

                except Exception as e:
                    print("[auto_calc_loop] error:", repr(e))
                    _time.sleep(60)

        t = threading.Thread(target=_auto_calc_loop, daemon=True)
        t.start()


    # 后台：APScheduler 定时触发同步任务。
    #   每周一 04:00 → TB小更新 + KB小更新
    #   API 用量由 ApiCallMonitor 自动管控：
    #     100% 硬限 → daily_sync_enabled='false' → is_sync_enabled() 为 false
    #
    #   ⚠️ 月大同步已关闭（2026-07-16），全量清表重拉改为手动操作。
    #   需要手动执行时，取消注释下面三行，重启服务即可：
    #     from base.sync.task_sync import tb_full_update_service
    #     project_id = ...  # 从 _resolve_sync_user_project() 获取
    #     tb_full_update_service({"projectId": project_id})
    from zoneinfo import ZoneInfo
    from apscheduler.schedulers.background import BackgroundScheduler

    _sync_scheduler = BackgroundScheduler(timezone=ZoneInfo("Asia/Shanghai"))

    def _resolve_sync_user_project() -> tuple:
        """从数据库人员表解析 userId，从配置解析 projectId。"""
        from base.dingtalk_client import get_config_projectids
        from base.organization.service import resolve_sync_operator_id

        user_id = resolve_sync_operator_id()

        projectids = get_config_projectids() or {}
        project_id = ""
        if isinstance(projectids, dict) and projectids:
            project_id = str(next(iter(projectids.values())) or "").strip()

        return user_id, project_id

    # ── 月大同步已关闭（2026-07-16），保留函数供手动恢复 ──
    # def _do_monthly_sync():
    #     """每月 1 号 04:00：刷新季度末 + KB大更新 + TB大更新。"""
    #     print("[auto_sync] === 每月1号：刷新季度末 + KB大更新 + TB大更新 ===")
    #
    #     from base.api_monitor import monitor as _api_monitor
    #     _api_monitor._ensure_state()
    #     from base.config.service import is_full_sync_enabled
    #     if not is_full_sync_enabled():
    #         print("[auto_sync] SKIP — full sync disabled (软限或硬限)")
    #         return
    #
    #     # 1) 刷新季度末
    #     print("[auto_sync] [1/3] 刷新季度末...")
    #     try:
    #         from base.config.service import update_endtime_service
    #         end_result = update_endtime_service()
    #         if end_result.get("success"):
    #             print(f"[auto_sync] end_time 已更新: {end_result.get('end_time', '?')}")
    #         else:
    #             print("[auto_sync] end_time 更新失败:", end_result.get("error", "unknown"))
    #     except Exception as e:
    #         print("[auto_sync] end_time 更新异常:", repr(e))
    #
    #     # 2) KB大更新
    #     print("[auto_sync] [2/3] KB大更新...")
    #     try:
    #         from ai.knowledge.auto_sync import kb_full_sync
    #         kb_result = kb_full_sync()
    #         if kb_result.get("ok"):
    #             s = kb_result.get("sync", {})
    #             e = kb_result.get("embed", {})
    #             print(f"[auto_sync] KB大更新 done  synced={s.get('totalSynced',0)}  failed={s.get('totalFailed',0)}  embed={e.get('embedded',0)}  elapsed={kb_result.get('durationSec',0):.1f}s")
    #         else:
    #             print("[auto_sync] KB大更新 failed:", kb_result.get("error", "unknown"))
    #     except Exception as e:
    #         print("[auto_sync] KB大更新 error:", repr(e))
    #
    #     # 3) TB大更新（清表全量重拉所有用户）
    #     print("[auto_sync] [3/3] TB大更新（清表全量）...")
    #     try:
    #         from base.sync.task_sync import tb_full_update_service
    #         user_id, project_id = _resolve_sync_user_project()
    #         if not project_id:
    #             print("[auto_sync] TB大更新 skipped: missing projectId")
    #         else:
    #             result = tb_full_update_service({"projectId": project_id})
    #             if result.get("success"):
    #                 d = result.get("data", {})
    #                 dev = d.get("dev", {})
    #                 issue = d.get("issue", {})
    #                 print(f"[auto_sync] TB大更新 done  users={d.get('user_count', 0)}  DEV: {dev.get('ok',0)}ok/{dev.get('fail',0)}fail  Issue: {issue.get('ok',0)}ok/{issue.get('fail',0)}fail  truncated={d.get('truncated', False)}")
    #             else:
    #                 print("[auto_sync] TB大更新 failed:", result.get("error", "unknown"))
    #     except Exception as e:
    #         print("[auto_sync] TB大更新 error:", repr(e))

    def _do_weekly_sync():
        """每周一 04:00：TB小更新 + KB小更新。"""
        print("[auto_sync] === 周一：TB团队增量 + KB小更新 ===")

        from base.api_monitor import monitor as _api_monitor
        _api_monitor._ensure_state()

        # 1) TB团队增量（导航组 + 对接组；列表及明细跨成员去重）
        print("[auto_sync] [1/2] TB团队小更新...")
        try:
            from base.sync.task_sync import benti_team_incremental_update_service
            from base.config.service import get_config_projectids

            projectids = get_config_projectids() or {}
            project_id = str(next(iter(projectids.values())) or "").strip()
            if not project_id:
                print("[auto_sync] TB团队小更新 aborted: missing projectId; KB小更新不会启动")
                return

            result = benti_team_incremental_update_service({"projectId": project_id})
            if not result.get("success"):
                print(
                    "[auto_sync] TB团队小更新 failed; KB小更新不会启动:",
                    result.get("error", "unknown"),
                )
                return

            data = result.get("data") or {}
            written = data.get("written") or {}
            print(
                "[auto_sync] TB团队小更新 done  users={} unique={} "
                "DEV={} Issue={}".format(
                    data.get("memberCount", 0),
                    data.get("uniqueTaskCount", 0),
                    written.get("dev", 0),
                    written.get("issue", 0),
                )
            )
        except Exception as e:
            print("[auto_sync] TB团队小更新 error; KB小更新不会启动:", repr(e))
            return

        # 2) KB小更新
        print("[auto_sync] [2/2] KB小更新...")
        try:
            from ai.knowledge.auto_sync import kb_incremental_sync
            result = kb_incremental_sync()
            if result.get("ok"):
                s = result.get("sync", {})
                e = result.get("embed", {})
                print(f"[auto_sync] KB小更新 done  synced={s.get('totalSynced',0)}  failed={s.get('totalFailed',0)}  embed={e.get('embedded',0)}  elapsed={result.get('durationSec',0):.1f}s")
            else:
                print("[auto_sync] KB小更新 failed:", result.get("error", "unknown"))
        except Exception as e:
            print("[auto_sync] KB小更新 error:", repr(e))

    # ── 月大同步已关闭（2026-07-16），取消 scheduler 注册 ──
    # _sync_scheduler.add_job(
    #     _do_monthly_sync, 'cron', day=1, hour=4, minute=0,
    #     id='monthly_sync', misfire_grace_time=3600,
    # )
    _sync_scheduler.add_job(
        _do_weekly_sync, 'cron', day_of_week='mon', hour=4, minute=0,
        id='weekly_sync', misfire_grace_time=3600,
    )
    _sync_scheduler.start()

    @app.teardown_appcontext
    def _remove_db_session(_exc):
        SessionLocal.remove()

    app.register_blueprint(api_bp)
    app.register_blueprint(dashboard_bp)

    @app.route("/")
    def vue_index():
        return send_from_directory(_VUE_DIR, "index.html")

    @app.route("/assets/<path:path>")
    def vue_assets(path: str):
        return send_from_directory(_VUE_DIR / "assets", path)

    @app.route("/<path:path>")
    def spa_fallback(path: str):
        # API 路由不走前端兜底，保持后端接口 404/405 语义。
        if path.startswith("api/"):
            abort(404)
        # 若是静态文件（如 favicon.svg、icons.svg）则直接返回文件。
        candidate = _VUE_DIR / path
        if candidate.exists() and candidate.is_file():
            return send_from_directory(_VUE_DIR, path)
        # 其余前端路由（如 /login）统一回落到 index.html。
        return send_from_directory(_VUE_DIR, "index.html")

    return app


app = create_app()


if __name__ == "__main__":
    debug_raw = env_bt("DEBUG", "false")
    debug = str(debug_raw).strip().lower() in {"1", "true", "yes", "y", "on"}
    # Flask 启动参数直接读 FLASK_RUN_* 环境变量，兼容 run_on_pc*.sh 的 export
    host = str(os.getenv("FLASK_RUN_HOST", "0.0.0.0")).strip() or "0.0.0.0"
    port_raw = str(os.getenv("FLASK_RUN_PORT", "5001")).strip() or "5001"
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid FLASK_RUN_PORT value: {port_raw}") from exc
    app.run(host=host, port=port, debug=debug)
