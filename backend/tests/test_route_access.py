import unittest
import sys
import types
from unittest.mock import patch

from flask import Blueprint, Flask, jsonify

sys.modules.setdefault("chinese_calendar", types.SimpleNamespace(
    is_workday=lambda _day: True,
    is_holiday=lambda _day: False,
))

from base.department.routes import register as register_department
from workhour.costhour.routes import register as register_costhour


def _ok(data):
    return jsonify({"code": 200, "error": "", "data": data}), 200


def _fail(message, code=400, data=None):
    return jsonify({"code": code, "error": message, "data": data or {}}), code


class BusinessRouteAccessTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        bp = Blueprint("access_test", __name__, url_prefix="/api/bt")
        register_costhour(bp, _ok, _fail)
        register_department(bp, _ok, _fail)
        app.register_blueprint(bp)
        self.client = app.test_client()

    def _login(self, *permissions):
        with self.client.session_transaction() as flask_session:
            flask_session["auth_user"] = {
                "user_id": "tester",
                "role": "manager",
                "permissionCodes": list(permissions),
            }

    def test_workday_routes_require_login(self):
        response = self.client.post("/api/bt/stats/workday_costhour/team_summary", json={})
        self.assertEqual(response.status_code, 401)

    def test_workday_routes_require_page_permission(self):
        self._login("page.performance")
        response = self.client.post("/api/bt/stats/attendance/save", json={})
        self.assertEqual(response.status_code, 403)

    @patch("workhour.costhour.routes.workday_costhour_team_summary_service", return_value={
        "success": True, "data": {"teams": []},
    })
    def test_workday_permission_allows_request(self, service):
        self._login("page.workday_costhour")
        response = self.client.post("/api/bt/stats/workday_costhour/team_summary", json={})
        self.assertEqual(response.status_code, 200)
        service.assert_called_once_with({})

    def test_department_overview_requires_admin_page_permission(self):
        self._login("page.workday_costhour")
        response = self.client.get("/api/bt/dashboard/department-overview")
        self.assertEqual(response.status_code, 403)

    @patch("base.department.routes.department_overview_service", return_value={
        "success": True, "data": {"rows": []},
    })
    def test_department_permission_allows_request(self, service):
        self._login("page.department_overview")
        response = self.client.get("/api/bt/dashboard/department-overview")
        self.assertEqual(response.status_code, 200)
        service.assert_called_once_with(start_date=None, end_date=None)


if __name__ == "__main__":
    unittest.main()
