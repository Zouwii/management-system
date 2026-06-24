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


    # 后台：北京时间 04:00 自动触发知识库同步 & TB 全量更新。
    # 每周一小同步（KB增量拉取），每月 1 号大同步（KB全量 + TB全量更新）。
    # API 用量由 ApiCallMonitor 自动管控：
    #   80% 软限 → knowledge_sync_enabled='partial' → is_full_sync_enabled() 为 false，阻止重量级同步
    #   100% 硬限 → knowledge_sync_enabled='false' → is_sync_enabled() 为 false，阻止所有同步
    global _AUTO_KNOWLEDGE_SYNC_THREAD_STARTED
    if not globals().get("_AUTO_KNOWLEDGE_SYNC_THREAD_STARTED"):
        _AUTO_KNOWLEDGE_SYNC_THREAD_STARTED = True

        def _auto_knowledge_sync_loop():
            from ai.knowledge.auto_sync import sync_all_and_embed
            from base.dingtalk_client import get_config_projectids, get_config_user_meta, get_config_userids
            from base.sync.task_sync import (
                DEFAULT_UPDATE_LOCK_KEY,
                _acquire_update_lock,
                _release_update_lock,
                full_update_service,
            )

            from base.api_monitor import BJ_TZ
            last_trigger_date = ""

            while True:
                try:
                    now_bj = datetime.now(BJ_TZ)
                    today = now_bj.strftime("%Y-%m-%d")

                    if now_bj.hour != 4 or now_bj.minute != 0 or last_trigger_date == today:
                        _time.sleep(30)
                        continue

                    # sync 开关（ApiCallMonitor 自动管控：true > partial > false）
                    from base.config.service import is_full_sync_enabled
                    if not is_full_sync_enabled():
                        print("[auto_sync_loop] SKIP — full sync disabled (软限或硬限)")
                        last_trigger_date = today
                        _time.sleep(30)
                        continue

                    weekday = now_bj.weekday()  # 0=周一
                    is_first_day = now_bj.day == 1

                    # 每月 1 号：KB 大同步 + TB 全量更新
                    if is_first_day:
                        print("[auto_sync_loop] === 每月1号：KB大同步 + TB全量更新 ===")

                        # 1) KB 大同步
                        print("[auto_sync_loop] [1/2] KB大同步...")
                        kb_result = sync_all_and_embed(full_sync=True)
                        if kb_result.get("ok"):
                            s = kb_result.get("sync", {})
                            e = kb_result.get("embed", {})
                            print(f"[auto_sync_loop] KB大同步 done  synced={s.get('totalSynced',0)}  failed={s.get('totalFailed',0)}  embed={e.get('embedded',0)}  elapsed={kb_result.get('durationSec',0):.1f}s")
                        else:
                            print("[auto_sync_loop] KB大同步 failed:", kb_result.get("error", "unknown"))

                        # 2) TB 全量更新
                        print("[auto_sync_loop] [2/2] TB全量更新...")
                        try:
                            user_id = ""
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
                                        user_id = str(one.get("userId") or "").strip()
                                        if user_id:
                                            break
                            if not user_id:
                                userids = get_config_userids() or {}
                                if isinstance(userids, dict) and userids:
                                    user_id = str(next(iter(userids.values())) or "").strip()

                            projectids = get_config_projectids() or {}
                            project_id = ""
                            if isinstance(projectids, dict) and projectids:
                                project_id = str(next(iter(projectids.values())) or "").strip()

                            if not user_id or not project_id:
                                print("[auto_sync_loop] TB全量 skipped: missing userId/projectId")
                            else:
                                owner = "auto_full_update@{}".format(int(_time.time()))
                                lock = _acquire_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
                                if not lock.get("ok"):
                                    print("[auto_sync_loop] TB全量 skipped: lock occupied")
                                else:
                                    try:
                                        out = full_update_service({
                                            "userId": user_id,
                                            "projectId": project_id,
                                            "force_refresh": True,
                                        })
                                        if out.get("success"):
                                            print(f"[auto_sync_loop] TB全量 success  projectId={project_id} userId={user_id}")
                                        else:
                                            print("[auto_sync_loop] TB全量 failed:", out.get("error", "unknown"))
                                    finally:
                                        _release_update_lock(DEFAULT_UPDATE_LOCK_KEY, owner)
                        except Exception as e:
                            print("[auto_sync_loop] TB全量 error:", repr(e))

                    # 每周一：KB 小同步
                    elif weekday == 0:
                        print("[auto_sync_loop] === 周一：KB小同步 ===")
                        result = sync_all_and_embed(full_sync=False)
                        if result.get("ok"):
                            s = result.get("sync", {})
                            e = result.get("embed", {})
                            print(f"[auto_sync_loop] KB小同步 done  synced={s.get('totalSynced',0)}  failed={s.get('totalFailed',0)}  embed={e.get('embedded',0)}  elapsed={result.get('durationSec',0):.1f}s")
                        else:
                            print("[auto_sync_loop] KB小同步 failed:", result.get("error", "unknown"))

                    last_trigger_date = today
                except Exception as e:
                    print("[auto_sync_loop] error:", repr(e))

                _time.sleep(30)

        t2 = threading.Thread(target=_auto_knowledge_sync_loop, daemon=True)
        t2.start()

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
