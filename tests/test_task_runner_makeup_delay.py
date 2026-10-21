import unittest
from unittest.mock import Mock, patch

from server import task_runner


class MakeupBatchDelayTest(unittest.TestCase):
    def test_replace_clock_in_ignores_custom_day_skip(self):
        api_client = Mock()
        config = Mock()

        values = {
            "config.clockIn.location.address": "test address",
            "config.clockIn.mode": "custom",
            "config.clockIn.specialClockIn": False,
            "config.clockIn.customDays": [],
            "config.clockIn.imageCount": 0,
            "config.clockIn.description": [],
            "config.clockIn.latitude": "30.1",
            "config.clockIn.longitude": "120.1",
            "config.clockIn.device": "android",
            "userInfo.userId": "u1",
            "userInfo.nikeName": "tester",
            "userInfo.orgJson.snowFlakeId": "s1",
        }
        config.get_value.side_effect = lambda key: values.get(key)
        api_client.get_checkin_records.return_value = []
        api_client.get_upload_token.return_value = "upload-token"

        result = task_runner.perform_clock_in(
            api_client,
            config,
            forced_checkin_type="START",
            target_time=task_runner.datetime(2026, 5, 22, 7, 30),
            replace=True,
        )

        self.assertNotEqual(result["status"], "skip")
        api_client.submit_clock_in_replace.assert_called_once()

    def test_perform_clock_in_makeup_many_waits_between_dates(self):
        api_client = Mock()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                {"status": "success", "message": "ok"},
                {"status": "success", "message": "ok"},
                {"status": "success", "message": "ok"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-20", "2026-05-21", "2026-05-22"],
                target_type="START",
                delay_seconds=1.5,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["details"]["请求间隔秒"], 1.5)
        self.assertEqual(makeup.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_any_call(1.5)

    def test_perform_clock_in_makeup_many_stops_without_replaying_after_rate_limit(self):
        api_client = Mock()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                {"status": "fail", "message": "打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229", "task_type": "补卡"},
                {"status": "success", "message": "ok", "task_type": "补卡"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-22"],
                target_type="START",
                delay_seconds=0,
                rate_limit_retries=2,
                rate_limit_retry_seconds=0.5,
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["details"]["频繁重试次数"], 0)
        self.assertEqual(makeup.call_count, 1)
        sleep.assert_not_called()

    def test_perform_clock_in_makeup_many_does_not_rotate_proxy_after_rate_limit(self):
        class ProxyApiClient:
            def __init__(self):
                self._proxy_urls = ["http://proxy-a.example:8080", "http://proxy-b.example:8080"]
                self.rotate_count = 0

            def rotate_proxy(self, reason=None):
                self.rotate_count += 1
                return True

        api_client = ProxyApiClient()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                {"status": "fail", "message": "打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229", "task_type": "补卡"},
                {"status": "success", "message": "ok", "task_type": "补卡"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-22"],
                target_type="START",
                delay_seconds=0,
                rate_limit_retries=2,
                rate_limit_retry_seconds=0.5,
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(api_client.rotate_count, 0)
        self.assertEqual(result["details"]["代理切换次数"], 0)
        sleep.assert_not_called()

    def test_perform_clock_in_makeup_many_does_not_refetch_proxy_after_rate_limit(self):
        class ProxyApiClient:
            def __init__(self):
                self._proxy_urls = []
                self._proxy_fetch_url = "http://proxy-api.example/getip?accessName=u&accessPassword=p"
                self.rotate_count = 0

            def rotate_proxy(self, reason=None):
                self.rotate_count += 1
                return True

        api_client = ProxyApiClient()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                {"status": "fail", "message": "打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229", "task_type": "补卡"},
                {"status": "success", "message": "ok", "task_type": "补卡"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-22"],
                target_type="START",
                delay_seconds=0,
                rate_limit_retries=2,
                rate_limit_retry_seconds=0.5,
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(api_client.rotate_count, 0)
        self.assertEqual(result["details"]["代理切换次数"], 0)
        sleep.assert_not_called()

    def test_perform_clock_in_makeup_many_cools_down_remaining_dates_after_rate_limit(self):
        api_client = Mock()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                {"status": "success", "message": "first", "task_type": "补卡"},
                {"status": "fail", "message": "打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229", "task_type": "补卡"},
                {"status": "success", "message": "second", "task_type": "补卡"},
                {"status": "success", "message": "third", "task_type": "补卡"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-20", "2026-05-21", "2026-05-22"],
                target_type="START",
                delay_seconds=1,
                rate_limit_retries=2,
                rate_limit_retry_seconds=0.5,
                rate_limit_cooldown_seconds=30,
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["details"]["频繁重试次数"], 0)
        self.assertEqual(result["details"]["频繁冷却次数"], 1)
        self.assertEqual(result["details"]["频繁冷却间隔秒"], 30)
        self.assertEqual(makeup.call_count, 2)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1])

    def test_perform_clock_in_makeup_many_retries_rate_limit_exception(self):
        api_client = Mock()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                RuntimeError("打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229"),
                {"status": "success", "message": "ok", "task_type": "补卡"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-22"],
                target_type="START",
                delay_seconds=0,
                rate_limit_retries=2,
                rate_limit_retry_seconds=0.5,
                rate_limit_cooldown_seconds=30,
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["details"]["频繁重试次数"], 0)
        self.assertEqual(makeup.call_count, 1)
        sleep.assert_not_called()

    def test_perform_clock_in_makeup_many_stops_remaining_dates_when_rate_limit_persists(self):
        api_client = Mock()
        config = Mock()

        with patch.object(task_runner, "perform_clock_in_makeup") as makeup, patch.object(task_runner.time, "sleep") as sleep:
            makeup.side_effect = [
                {"status": "success", "message": "first", "task_type": "补卡"},
                {"status": "fail", "message": "打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229", "task_type": "补卡"},
                {"status": "fail", "message": "打卡失败: IP请求过于频繁，请稍后再试:111.23.44.229", "task_type": "补卡"},
            ]

            result = task_runner.perform_clock_in_makeup_many(
                api_client,
                config,
                ["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"],
                target_type="START",
                delay_seconds=1,
                rate_limit_retries=1,
                rate_limit_retry_seconds=0.5,
                rate_limit_cooldown_seconds=30,
            )

        self.assertEqual(result["status"], "fail")
        self.assertIn("暂停剩余日期", result["message"])
        self.assertTrue(result["details"]["因频繁请求提前停止"])
        self.assertEqual(result["details"]["未执行"], 2)
        self.assertEqual(result["details"]["成功"], 1)
        self.assertEqual(result["details"]["失败"], 1)
        self.assertEqual(result["details"]["跳过"], 2)
        self.assertEqual(makeup.call_count, 2)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1])
        self.assertEqual(result["items"][2]["status"], "skip")
        self.assertIn("频繁", result["items"][2]["message"])


if __name__ == "__main__":
    unittest.main()
