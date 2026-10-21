import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from server import api
from server.models import User


class FakeRequest:
    headers = {}
    client = SimpleNamespace(host="127.0.0.1")


class ApiRunRateLimitScopeTest(unittest.TestCase):
    def test_report_run_requests_do_not_use_internal_run_rate_limit(self):
        for task_type in ("daily_report", "weekly_report", "monthly_report", "report"):
            with self.subTest(task_type=task_type):
                req = api.AppRunRequest(task_type=task_type, force_report=True, target_period="2026-05-22")

                self.assertFalse(api._should_rate_limit_run_request(req))

    def test_non_report_run_requests_still_use_internal_run_rate_limit(self):
        for task_type in (None, "", "clock_in", "clock_in_makeup"):
            with self.subTest(task_type=task_type):
                req = api.AppRunRequest(task_type=task_type)

                self.assertTrue(api._should_rate_limit_run_request(req))

    def test_admin_report_run_endpoint_does_not_call_internal_rate_limit(self):
        user = User(id=7, phone="tester", password="secret")
        session = Mock()
        session.get.return_value = user
        req = api.AppRunRequest(task_type="weekly_report", force_report=True, target_period="2026-05-22")

        with (
            patch.object(api, "_rate_limit") as rate_limit,
            patch.object(api, "user_to_config", return_value={"config": {}}),
            patch.object(api, "run_task_by_config", return_value=[{"status": "success", "task_type": "周报提交"}]),
            patch.object(api, "apply_execution_results_to_user", return_value="Success"),
        ):
            result = api.run_user_task(
                request=FakeRequest(),
                session=session,
                user_id=7,
                req=req,
                operator={"sub": "admin"},
            )

        self.assertEqual(result["results"][0]["task_type"], "周报提交")
        rate_limit.assert_not_called()

    def test_app_report_run_endpoint_does_not_call_internal_rate_limit(self):
        user = User(id=8, phone="tester", password="secret")
        req = api.AppRunRequest(task_type="weekly_report", force_report=True, target_period="2026-05-22")

        with (
            patch.object(api, "_rate_limit") as rate_limit,
            patch.object(api, "_get_authed_app_user", return_value=Mock()),
            patch.object(api, "_get_bound_task_user", return_value=user),
            patch.object(api, "user_to_config", return_value={"config": {}}),
            patch.object(api, "run_task_by_config", return_value=[{"status": "success", "task_type": "周报提交"}]),
            patch.object(api, "apply_execution_results_to_user", return_value="Success"),
        ):
            result = api.app_run(
                request=FakeRequest(),
                session=Mock(),
                payload={"sub": "app-user"},
                req=req,
            )

        self.assertEqual(result["results"][0]["task_type"], "周报提交")
        rate_limit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
