import sys
import types
import unittest

sys.modules.setdefault("chinese_calendar", types.SimpleNamespace(
    is_workday=lambda _day: True,
    is_holiday=lambda _day: False,
))

from workhour.personal.routes import _public_personal_hours_payload


class PersonalHoursContractV2Tests(unittest.TestCase):
    def test_public_payload_uses_stable_organization_fields(self):
        result = _public_personal_hours_payload({
            "memberOptions": [{
                "id": "u1",
                "name": "张三",
                "userId": "u1",
                "team": "导航组",
                "teamId": "0",
                "teamCode": "NAV",
                "teamName": "导航组",
                "character": 3,
                "jobRoleCode": "APPLICATION_ENGINEER",
                "isNavLead": False,
                "isServoLead": False,
            }],
            "workhourRoleCoefficients": {
                "SOFTWARE_ENGINEER": 0.7,
                "APPLICATION_ENGINEER": 1.0,
            },
        })

        self.assertEqual(result["memberOptions"], [{
            "id": "u1",
            "name": "张三",
            "userId": "u1",
            "teamCode": "NAV",
            "teamName": "导航组",
            "jobRoleCode": "APPLICATION_ENGINEER",
            "jobRoleName": "应用工程师",
        }])
        self.assertEqual(result["workhourRoleCoefficients"], {
            "SOFTWARE_ENGINEER": 0.7,
            "APPLICATION_ENGINEER": 1.0,
        })


if __name__ == "__main__":
    unittest.main()
