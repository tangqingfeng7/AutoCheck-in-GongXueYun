import unittest
from unittest.mock import Mock, patch

from server import task_runner


def _config_data():
    return {
        "config": {
            "pushNotifications": [],
            "clockIn": {"schedule": {"startTime": "07:30", "endTime": "18:00"}},
            "reportSettings": {
                "daily": {"enabled": False},
                "weekly": {"enabled": False},
                "monthly": {"enabled": False},
            },
        },
        "userInfo": {
            "token": "token",
            "expiredTime": "1893456000",
            "nikeName": "tester",
            "userType": "student",
        },
        "planInfo": {"planId": "plan-1"},
    }


class TaskRunnerTaskSelectionTest(unittest.TestCase):
    def test_default_task_run_does_not_include_clockin_makeup(self):
        with (
            patch.object(task_runner, "ApiClient") as api_client_cls,
            patch.object(task_runner, "MessagePusher") as pusher_cls,
            patch.object(task_runner, "_load_global_smtp_settings", return_value={}),
            patch.object(task_runner, "perform_clock_in", return_value={"status": "success", "task_type": "打卡", "message": "ok"}) as clock_in,
            patch.object(task_runner, "perform_clock_in_makeup", return_value={"status": "success", "task_type": "补卡", "message": "bad"}) as makeup,
            patch.object(task_runner, "submit_daily_report", return_value={"status": "skip", "task_type": "日报提交", "message": "skip"}),
            patch.object(task_runner, "submit_weekly_report", return_value={"status": "skip", "task_type": "周报提交", "message": "skip"}),
            patch.object(task_runner, "submit_monthly_report", return_value={"status": "skip", "task_type": "月报提交", "message": "skip"}),
        ):
            pusher_cls.return_value.push = Mock()

            results = task_runner.run_task_by_config(_config_data(), forced_checkin_type="START")

        clock_in.assert_called_once()
        makeup.assert_not_called()
        api_client_cls.return_value.enable_proxy.assert_not_called()
        self.assertNotIn("补卡", [item.get("task_type") for item in results])

    def test_explicit_clockin_makeup_task_can_be_run_manually(self):
        with (
            patch.object(task_runner, "ApiClient") as api_client_cls,
            patch.object(task_runner, "MessagePusher") as pusher_cls,
            patch.object(task_runner, "_load_global_smtp_settings", return_value={}),
            patch.object(task_runner, "perform_clock_in") as clock_in,
            patch.object(task_runner, "perform_clock_in_makeup", return_value={"status": "success", "task_type": "补卡", "message": "ok"}) as makeup,
        ):
            pusher_cls.return_value.push = Mock()

            results = task_runner.run_task_by_config(
                _config_data(),
                specific_task_type="clock_in_makeup",
                target_period="2026-05-22",
            )

        clock_in.assert_not_called()
        makeup.assert_called_once()
        api_client_cls.return_value.enable_proxy.assert_not_called()
        self.assertEqual([item.get("task_type") for item in results], ["补卡"])


if __name__ == "__main__":
    unittest.main()
