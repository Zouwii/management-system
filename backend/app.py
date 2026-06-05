from base.app import create_app, app as application
import os
app = application
if __name__ == "__main__":
    port = int(os.environ.get("FLASK_RUN_PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "1") not in ("0", "false", "False")
    app.run(host="0.0.0.0", port=port, debug=debug)
