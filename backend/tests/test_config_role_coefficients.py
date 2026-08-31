import unittest
from unittest.mock import patch

from flask import Blueprint, Flask, jsonify

from base.config.routes import register as register_config
from base.config.service import _parse_role_coefficients


def _ok(data):
    return jsonify({"code": 200, "error": "", "data": data}), 200


def _fail(message, code=400, data=None):
    return jsonify({"code": code, "error": message, "data": data or {}}), code


class ConfigRoleCoefficientTests(unittest.TestCase):
    def test_parser_accepts_stable_roles_and_rejects_legacy_keys(self):
        result = _parse_role_coefficients({
            "APPLICATION_ENGINEER": 1,
            "3": 0.5,
            "UNKNOWN": 2,
        })
        self.assertEqual(result, {"APPLICATION_ENGINEER": 1.0})

    @patch("base.config.routes.get_workhour_role_coefficients_service", return_value={
        "success": True,
        "workhour_role_coefficients": {"APPLICATION_ENGINEER": 1.0},
    })
    def test_http_contract_exposes_only_new_endpoint(self, _service):
        app = Flask(__name__)
        bp = Blueprint("config_test", __name__, url_prefix="/api/bt")
        register_config(bp, _ok, _fail)
        app.register_blueprint(bp)
        client = app.test_client()

        response = client.get("/api/bt/config/workhour_role_coefficients")
        self.assertEqual(response.status_code, 200)
        self.assertIn("APPLICATION_ENGINEER", response.get_json()["data"]["workhour_role_coefficients"])
        self.assertEqual(client.get("/api/bt/config/workhour_character_coefficients").status_code, 404)
        self.assertEqual(client.get("/api/bt/config/workhour_coefficient").status_code, 404)


if __name__ == "__main__":
    unittest.main()
