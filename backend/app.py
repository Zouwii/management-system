import os

from flask import Flask, send_from_directory
from flask_cors import CORS

from api import api_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # 前端先和后端同源部署时可以不需要 CORS；
    # 这里保留允许，方便你之后把前端单独跑在另一个端口。
    CORS(app, resources={r"/api/b1/*": {"origins": "*"}})

    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return send_from_directory(
            os.path.join(app.root_path, "static"), "index.html"
        )

    @app.route("/static/<path:path>")
    def static_files(path: str):
        return send_from_directory(os.path.join(app.root_path, "static"), path)

    return app


app = create_app()


if __name__ == "__main__":
    # 端口固定到 5001，避免和 tb_tool_backend 默认 5000 冲突
    debug_raw = os.getenv("TB_TOOL_B1_DEBUG", "false")
    debug = str(debug_raw).strip().lower() in {"1", "true", "yes", "y", "on"}
    app.run(host="0.0.0.0", port=5001, debug=debug)

