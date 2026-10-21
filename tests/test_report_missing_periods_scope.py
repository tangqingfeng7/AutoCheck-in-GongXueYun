import unittest
from unittest.mock import patch

from server import api
from server.models import User


class ReportMissingPeriodsScopeTest(unittest.TestCase):
    def test_disabled_report_type_returns_empty_without_remote_query(self):
        user = User(
            phone="",
            password="",
            reportSettings={
                "daily": {"enabled": False},
                "weekly": {"enabled": True},
                "monthly": {"enabled": False},
            },
        )

        with patch.object(api, "ApiClient") as api_client_cls:
            result = api._get_missing_report_periods_for_user(user, "daily")

        self.assertTrue(result["ok"])
        self.assertTrue(result["disabled"])
        self.assertEqual(result["options"], [])
        api_client_cls.assert_not_called()

    def test_enabled_report_type_still_requires_account_before_remote_query(self):
        user = User(
            phone="",
            password="",
            reportSettings={"weekly": {"enabled": True}},
        )

        with self.assertRaises(api.HTTPException) as ctx:
            api._get_missing_report_periods_for_user(user, "weekly")

        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
