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

    # 后台：根据 config 表里的自动计算设置，到点触发“更新数据”
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

            while True:
                try:
                    cfg = get_workhour_auto_calc_service() or {}
                    if not cfg.get("auto_calc_enabled"):
                        _time.sleep(30)
                        continue

                    auto_time = str(cfg.get("auto_calc_time") or "").strip()
                    parts = auto_time.split(":")
                    if len(parts) != 2:
                        _time.sleep(30)
                        continue

                    hh = int(parts[0])
                    mm = int(parts[1])
                    now = datetime.now()
                    if now.hour != hh or now.minute != mm:
                        _time.sleep(30)
                        continue

                    # 用 last_update_time 的日期去重：确保同一天只触发一次
                    today = now.strftime("%Y-%m-%d")
                    lu = get_last_update_time_service() or {}
                    last = lu.get("last_update_time") or ""
                    if last:
                        try:
                            last_dt = datetime.fromisoformat(last)
                            last_local = last_dt.astimezone().strftime("%Y-%m-%d")
                            if last_local == today:
                                _time.sleep(30)
                                continue
                        except Exception:
                            # 解析失败：直接放行触发（由 touch 接管 last_update_time）
                            pass

                    # 触发一次“更新数据”（更新 last_update_time）
                    touch_last_update_time_service()
                except Exception as e:
                    print("[auto_calc_loop] error:", repr(e))

                # 稍等，避免同一分钟内多次触发
                _time.sleep(30)

        t = threading.Thread(target=_auto_calc_loop, daemon=True)
        t.start()

    # 后台：北京时间每天 03:00 自动触发一次“全量更新”。
    # 使用更新锁避免与手动更新并发冲突。
    global _AUTO_FULL_UPDATE_THREAD_STARTED
    if not globals().get("_AUTO_FULL_UPDATE_THREAD_STARTED"):
        _AUTO_FULL_UPDATE_THREAD_STARTED = True

        def _auto_full_update_loop():
            from base.dingtalk_client import get_config_projectids, get_config_user_meta, get_config_userids
            from base.sync.task_sync import (
                DEFAULT_UPDATE_LOCK_KEY,
                _acquire_update_lock,
                _release_update_lock,
                full_update_service,
            )

            bj_tz = timezone(timedelta(hours=8))
            last_trigger_date = ""

            def _resolve_operator_user_id() -> str:
                meta = get_config_user_meta() or {}
                if isinstance(meta, dict):
                    for _name, one in meta.items():
                        if not isinstance(one, dict):
                            continue
                        try:
                            ch = int(one.get("character", 1))
                        except Exception:
                            ch = 1
                        if ch == 0:
                            uid = str(one.get("userId") or "").strip()
                            if uid:
                                return uid

                userids = get_config_userids() or {}
                if isinstance(userids, dict) and userids:
                    return str(next(iter(userids.values())) or "").strip()
                return ""

            # sync_disabled：若标记文件存在，直接退出定时循环，不轮询
            _flag_path = Path(__file__).resolve().parent.parent / "runtime" / "sync_disabled"
            if _flag_path.exists():
                print("[auto_full_update_loop] SKIP — sync is disabled (runtime/sync_disabled exists)")
                return

            while True:
                try:
                    now_bj = datetime.now(bj_tz)
                    today = now_bj.strftime("%Y-%m-%d")

                    # 每天北京时间 03:00 触发一次。
                    if now_bj.hour == 3 and now_bj.minute == 0 and last_trigger_date != today:
                        user_id = _resolve_operator_user_id()
                        projectids = get_config_projectids() or {}
                        project_id = ""
                        if isinstance(projectids, dict) and projectids:
                            project_id = str(next(iter(projectids.values())) or "").strip()

                        if not user_id or not project_id:
                            print(
                                "[auto_full_update_loop] skipped: missing userId/projectId in ids config",
                                {"userId": user_id, "projectId": project_id},
                            )
                            last_trigger_date = today
                            _time.sleep(30)
                            continue

                        owner = "auto_full_update@{}".format(int(_time.time()))
                        lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
                        if not lock.get("ok"):
                            print("[auto_full_update_loop] skipped: update lock occupied", lock.get("lock") or {})
                            last_trigger_date = today
                            _time.sleep(30)
                            continue

                        try:
                            out = full_update_service(
                                {
                                    "userId": user_id,
                                    "projectId": project_id,
                                    "force_refresh": True,
                                }
                            )
                            if out.get("success"):
                                print(
                                    "[auto_full_update_loop] success",
                                    {
                                        "date": today,
                                        "projectId": project_id,
                                        "userId": user_id,
                                    },
                                )
                            else:
                                print("[auto_full_update_loop] failed", out.get("error", "unknown error"))
                        finally:
                            _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)

                        last_trigger_date = today
                except Exception as e:
                    print("[auto_full_update_loop] error:", repr(e))

                _time.sleep(30)

        t2 = threading.Thread(target=_auto_full_update_loop, daemon=True)
        t2.start()

    # 后台：北京时间每天 04:00 自动触发知识库同步。
    # 每天小同步（增量拉新文档），每月 1 号大同步（全量对比更新）。
    global _AUTO_KNOWLEDGE_SYNC_THREAD_STARTED
    if not globals().get("_AUTO_KNOWLEDGE_SYNC_THREAD_STARTED"):
        _AUTO_KNOWLEDGE_SYNC_THREAD_STARTED = True

        def _auto_knowledge_sync_loop():
            from ai.knowledge.auto_sync import sync_all_and_embed

            bj_tz = timezone(timedelta(hours=8))
            last_trigger_date = ""

            while True:
                try:
                    now_bj = datetime.now(bj_tz)
                    today = now_bj.strftime("%Y-%m-%d")

                    # 小同步：每周一/周四 04:00；大同步：每月1号 04:00
                    if now_bj.hour == 4 and now_bj.minute == 0 and last_trigger_date != today:
                        weekday = now_bj.weekday()  # 0=周一, 3=周四
                        # 每月 1 号做大同步，周一/周四做小同步
                        if now_bj.day == 1:
                            full_sync = True
                            mode = "大同步(全量)"
                        elif weekday in (0, 3):
                            full_sync = False
                            mode = "小同步(增量)"
                        else:
                            last_trigger_date = today
                            _time.sleep(30)
                            continue
                        print(f"[auto_knowledge_sync_loop] starting {mode}")
                        result = sync_all_and_embed(full_sync=full_sync)
                        if result.get("ok"):
                            sync_info = result.get("sync", {})
                            embed_info = result.get("embed", {})
                            print(
                                "[auto_knowledge_sync_loop] done"
                                "  sync: {} synced, {} failed"
                                "  skipped: {} wb, {} cached, {} unchanged"
                                "  embed: {} embedded, {} skipped"
                                "  elapsed: {:.1f}s".format(
                                    sync_info.get("totalSynced", 0),
                                    sync_info.get("totalFailed", 0),
                                    sync_info.get("skippedWorkbooks", 0),
                                    sync_info.get("skippedCached", 0),
                                    sync_info.get("skippedUnchanged", 0),
                                    embed_info.get("embedded", 0),
                                    embed_info.get("skipped", 0),
                                    result.get("durationSec", 0),
                                )
                            )
                        else:
                            print("[auto_knowledge_sync_loop] failed:", result.get("error", "unknown error"))

                        last_trigger_date = today
                except Exception as e:
                    print("[auto_knowledge_sync_loop] error:", repr(e))

                _time.sleep(30)

        t3 = threading.Thread(target=_auto_knowledge_sync_loop, daemon=True)
        t3.start()

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
