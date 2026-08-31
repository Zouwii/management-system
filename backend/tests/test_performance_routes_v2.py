import unittest
from unittest.mock import patch

from flask import Blueprint, Flask, jsonify

from performance.routes import register


def _ok(data):
    return jsonify({"code": 200, "error": "", "data": data}), 200


def _fail(message, code=400, data=None):
    return jsonify({"code": code, "error": message, "data": data or {}}), code


class PerformanceRoutesV2Tests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        bp = Blueprint("perf_test", __name__, url_prefix="/api/bt")
        register(bp, _ok, _fail)
        app.register_blueprint(bp)
        self.client = app.test_client()

    def _login(self, *permissions):
        with self.client.session_transaction() as flask_session:
            flask_session["auth_user"] = {
                "user_id": "tester",
                "role": "manager",
                "permissionCodes": list(permissions),
            }

    @patch("performance.routes.query_quarter_performance_service", return_value={
        "success": True, "data": {"results": [], "count": 0},
    })
    def test_query_accepts_team_code(self, query):
        self._login("page.performance")
        response = self.client.get("/api/bt/perf/query?year=2026&quarter=3&teamCode=NAV")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(query.call_args.args[0]["teamCode"], "NAV")

    @patch("performance.routes.query_quarter_performance_service", return_value={
        "success": True, "data": {"results": [], "count": 0},
    })
    def test_query_ignores_legacy_team_key(self, query):
        self._login("page.performance")
        response = self.client.get("/api/bt/perf/query?year=2026&quarter=3&teamKey=nav")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(query.call_args.args[0]["teamCode"], "")

    @patch("performance.routes.list_team_import_users_service", return_value={
        "success": True, "data": {"members": [], "count": 0},
    })
    def test_import_users_accepts_team_code(self, list_users):
        self._login("button.review_member")
        response = self.client.get(
            "/api/bt/perf/team-import-users?year=2026&quarter=3&teamCode=INTEGRATION"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list_users.call_args.args[0]["teamCode"], "INTEGRATION")

    def test_query_requires_login(self):
        response = self.client.get("/api/bt/perf/query?year=2026&quarter=3")
        self.assertEqual(response.status_code, 401)

    def test_write_requires_review_permission(self):
        self._login("page.performance")
        response = self.client.post("/api/bt/perf/batch-import", json={"members": []})
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
