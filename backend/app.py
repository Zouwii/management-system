import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

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
