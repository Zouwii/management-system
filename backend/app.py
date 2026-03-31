import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

import threading
import time as _time
from datetime import datetime

from flask import Flask, send_from_directory
from flask_cors import CORS

from api import api_bp
from db import SessionLocal, init_db
from db.config import env_bt

_VUE_DIR = Path(__file__).resolve().parent / "static" / "vue"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    CORS(app, resources={r"/api/bt/*": {"origins": "*"}})

    init_db()

    # 后台：根据 config 表里的自动计算设置，到点触发“更新数据”
    # 注意：用 daemon thread，且通过模块级标记避免重复启动。
    global _AUTO_CALC_THREAD_STARTED
    if not globals().get("_AUTO_CALC_THREAD_STARTED"):
        _AUTO_CALC_THREAD_STARTED = True

        def _auto_calc_loop():
            from services.config_service import (
                get_workhour_auto_calc_service,
                touch_last_update_time_service,
                get_time_range_service,
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
                    tr = get_time_range_service() or {}
                    last = tr.get("last_update_time") or ""
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

    @app.teardown_appcontext
    def _remove_db_session(_exc):
        SessionLocal.remove()

    app.register_blueprint(api_bp)

    @app.route("/")
    def vue_index():
        return send_from_directory(_VUE_DIR, "index.html")

    @app.route("/assets/<path:path>")
    def vue_assets(path: str):
        return send_from_directory(_VUE_DIR / "assets", path)

    return app


app = create_app()


if __name__ == "__main__":
    debug_raw = env_bt("DEBUG", "false")
    debug = str(debug_raw).strip().lower() in {"1", "true", "yes", "y", "on"}
    app.run(host="0.0.0.0", port=5001, debug=debug)
