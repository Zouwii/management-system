import unittest
from unittest.mock import patch

from flask import Blueprint, Flask, jsonify

from base.organization.routes import register


def _ok(data):
    return jsonify({"code": 200, "error": "", "data": data}), 200


def _fail(message, code=400, data=None):
    return jsonify({"code": code, "error": message, "data": data or {}}), code


class OrganizationRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        bp = Blueprint("test_api", __name__, url_prefix="/api/bt")
        register(bp, _ok, _fail)
        app.register_blueprint(bp)
        self.client = app.test_client()

    def _login(self):
        with self.client.session_transaction() as flask_session:
            flask_session["auth_user"] = {
                "user_id": "tester",
                "role": "manager",
                "permissionCodes": ["page.workday_costhour"],
            }

    @patch("base.organization.routes.list_scope_members", return_value=[{
        "userId": "u1", "userName": "张三", "name": "张三",
        "teamCode": "NAV", "teamName": "导航组", "teamId": "0", "team": "导航组",
        "jobRoleCode": "SOFTWARE_ENGINEER", "jobRoleName": "软件开发工程师",
        "character": 1, "isNavLead": False, "isServoLead": False,
    }])
    @patch("base.organization.routes.list_scope_teams", return_value={
        "scopeCode": "ATTENDANCE",
        "teams": [{"code": "NAV", "name": "导航组", "teamCode": "NAV", "teamName": "导航组", "teamId": "0"}],
    })
    def test_options_endpoint(self, teams, members):
        self._login()
        response = self.client.get("/api/bt/organization/scopes/ATTENDANCE/options")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["scopeCode"], "ATTENDANCE")
        self.assertEqual(data["teams"], [{"teamCode": "NAV", "teamName": "导航组"}])
        self.assertEqual(data["members"], [{
            "userId": "u1", "userName": "张三",
            "teamCode": "NAV", "teamName": "导航组",
            "jobRoleCode": "SOFTWARE_ENGINEER", "jobRoleName": "软件开发工程师",
        }])
        self.assertEqual(members.call_count, 1)

    @patch("base.organization.routes.list_scope_members", return_value=[])
    def test_legacy_team_query_parameter_is_ignored(self, members):
        self._login()
        response = self.client.get("/api/bt/organization/scopes/ATTENDANCE/members?team=导航组")
        self.assertEqual(response.status_code, 200)
        members.assert_called_once_with("ATTENDANCE", None)

    @patch("base.organization.routes.list_scope_members", side_effect=ValueError("unknown team: X"))
    def test_invalid_filter_returns_bad_request(self, _members):
        self._login()
        response = self.client.get("/api/bt/organization/scopes/ATTENDANCE/members?teamCode=X")
        self.assertEqual(response.status_code, 400)
        self.assertIn("unknown team", response.get_json()["error"])

    def test_members_endpoint_requires_login(self):
        response = self.client.get("/api/bt/organization/scopes/ATTENDANCE/members")
        self.assertEqual(response.status_code, 401)

    def test_scope_endpoint_requires_matching_permission(self):
        with self.client.session_transaction() as flask_session:
            flask_session["auth_user"] = {
                "user_id": "employee",
                "role": "employee",
                "permissionCodes": ["page.performance"],
            }
        response = self.client.get("/api/bt/organization/scopes/ATTENDANCE/members")
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
