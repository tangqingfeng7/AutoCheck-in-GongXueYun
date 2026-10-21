import json
import tempfile
import unittest
from email import message_from_bytes
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException

from server import api, task_runner
from server.coreApi.MainLogicApi import ApiClient
from server.models import AuditLog, User
from server.user_runtime import apply_execution_results_to_user
from server.util.Config import ConfigManager
from server.util.MessagePush import MessagePusher


SAFE_REGISTRATION = {
    "outRegisterNo": "test-123-AbCd",
    "registerUrl": "alipays://platformapi/startapp?appId=test",
}


class FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get_value(self, key):
        return self.values.get(key)


def build_api_client():
    client = ApiClient.__new__(ApiClient)
    client.config = FakeConfig(
        {
            "config.device": "test-device",
            "config.clockIn.location": {
                "address": "test address",
                "latitude": "30.1",
                "longitude": "120.1",
            },
            "config.clockIn.location.address": "test address",
            "planInfo.planId": "test-plan",
            "userInfo.roleKey": "student",
            "userInfo.token": "test-token",
            "userInfo.userId": "test-user",
            "userInfo.userType": "student",
        }
    )
    client.max_retries = 1
    return client


def build_checkin_info():
    return {
        "type": "START",
        "attachments": None,
        "description": "test description",
        "createTime": "2026-07-15 08:00:00",
        "attendenceTime": "2026-07-15 08:00:00",
    }


def build_task_config():
    return FakeConfig(
        {
            "config.clockIn.customDays": [],
            "config.clockIn.description": [],
            "config.clockIn.imageCount": 0,
            "config.clockIn.location.address": "test address",
            "config.clockIn.mode": "none",
            "config.clockIn.specialClockIn": False,
            "userInfo.nikeName": "Test User",
            "userInfo.orgJson.snowFlakeId": "test-org",
            "userInfo.userId": "test-user",
        }
    )


def build_task_api_client(submit_result, *, replace=False):
    client = Mock()
    client.get_checkin_records.return_value = []
    client.get_upload_token.return_value = "test-upload-token"
    client.create_alipay_clockin_verification.return_value = dict(SAFE_REGISTRATION)
    if replace:
        client.submit_clock_in_replace.return_value = submit_result
    else:
        client.submit_clock_in.return_value = submit_result
    if submit_result.get("status") == "success":
        def submit_and_record(payload):
            client.get_checkin_records.return_value = [{"type": payload["type"], "createTime": payload["createTime"]}]
            return submit_result
        (client.submit_clock_in_replace if replace else client.submit_clock_in).side_effect = submit_and_record
    return client


class AlipayApiClientTest(unittest.TestCase):
    def test_official_android_v5416_headers_are_present(self):
        self.assertEqual(ApiClient.DEFAULT_HEADERS["devices"], "android")
        self.assertEqual(ApiClient.DEFAULT_HEADERS["packageVersion"], "5.41.6")
        self.assertEqual(ApiClient.DEFAULT_HEADERS["buildNumber"], "50291")
        self.assertEqual(ApiClient.DEFAULT_HEADERS["codeVersion"], "292")
        self.assertEqual(
            ApiClient.DEFAULT_HEADERS["Client_Id"],
            ApiClient.ALIPAY_VERIFICATION_CLIENT_ID,
        )

    def test_post_request_returns_clockin_business_responses(self):
        client = build_api_client()
        response = Mock(status_code=200, text="")
        response.raise_for_status.return_value = None

        for msg in ("302", "304"):
            with self.subTest(msg=msg):
                response.json.return_value = {"code": 200, "msg": msg, "data": "test"}
                client.session = Mock()
                client.session.post.return_value = response
                with patch.object(client, "_proxy_request_kwargs", return_value={}):
                    result = client._post_request("test/path", {}, {})
                self.assertEqual(result["msg"], msg)

    def test_attendance_submission_is_not_replayed_after_network_error(self):
        client = build_api_client()
        client.max_retries = 5
        client.session = Mock()
        client.session.post = Mock(side_effect=requests.Timeout("timeout"))
        client.rotate_proxy = Mock(return_value=True)

        with patch.object(client, "_proxy_request_kwargs", return_value={}):
            with self.assertRaisesRegex(ValueError, "结果可能已被服务器接收"):
                client._post_request("attendence/clock/v6/save", {}, {})

        client.session.post.assert_called_once()
        client.rotate_proxy.assert_not_called()

    def test_attendance_submission_never_uses_enabled_proxy(self):
        client = build_api_client()
        response = Mock(status_code=200, text="")
        response.json.return_value = {"code": 200, "msg": "success", "data": None}
        response.raise_for_status.return_value = None
        client.session = Mock()
        client.session.post.return_value = response

        with patch.object(
            client,
            "_proxy_request_kwargs",
            return_value={
                "proxies": {
                    "http": "http://proxy.example:8080",
                    "https": "http://proxy.example:8080",
                }
            },
        ) as proxy_kwargs:
            result = client._post_request("attendence/clock/v6/save", {}, {})

        self.assertEqual(result["code"], 200)
        proxy_kwargs.assert_not_called()
        self.assertNotIn("proxies", client.session.post.call_args.kwargs)

    def test_verification_email_contains_inline_qr_and_open_links(self):
        sent = []

        class FakeSMTP:
            def __init__(self, host, port):
                self.host = host
                self.port = port

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def login(self, username, password):
                self.username = username

            def send_message(self, message):
                sent.append(message)

        pusher = MessagePusher(
            [
                {
                    "type": "SMTP",
                    "enabled": True,
                    "username": "sender@qq.com",
                    "password": "smtp-secret",
                    "to": "recipient@qq.com",
                    "from": "工学云签到通知",
                }
            ]
        )
        result = {
            "status": "fail",
            "message": "需要完成支付宝安全验证，请验证后继续打卡",
            "task_type": "打卡",
            "details": {
                "verification_type": "account",
                "target_type": "START",
                "registerUrl": "alipays://platformapi/startapp?appId=test",
            },
        }

        with patch.object(MessagePusher, "_deliver_smtp", side_effect=lambda cfg, msg: sent.append(msg)):
            pusher.push([result])

        self.assertEqual(len(sent), 1)
        raw = sent[0].as_bytes()
        parsed = message_from_bytes(raw)
        self.assertTrue(parsed.is_multipart())
        html_parts = [part for part in parsed.walk() if part.get_content_type() == "text/html"]
        image_parts = [part for part in parsed.walk() if part.get_content_type() == "image/png"]
        self.assertEqual(len(html_parts), 1)
        self.assertEqual(len(image_parts), 1)
        body = html_parts[0].get_payload(decode=True).decode("utf-8")
        self.assertIn("https://ds.alipay.com/", body)
        self.assertIn("alipays://platformapi/startapp?appId=test", body)
        self.assertEqual(image_parts[0].get("Content-ID"), "<gxy-verification-qr>")

    def test_verification_email_rejects_non_alipay_link(self):
        result = {
            "status": "fail",
            "task_type": "打卡",
            "details": {
                "verification_type": "account",
                "registerUrl": "https://example.test/not-alipay",
            },
        }
        self.assertEqual(MessagePusher._verification_results([result]), [])

    def test_background_smtp_settings_decrypt_stored_authorization_code(self):
        stored = {
            "smtp": {
                "enabled": True,
                "username": "sender@qq.com",
                "password": "encrypted-value",
                "from": "工学云签到通知",
            }
        }
        with patch.object(task_runner, "decrypt_secret", return_value="plain-auth-code") as decrypt:
            decoded = task_runner._decode_stored_smtp_settings(stored)

        decrypt.assert_called_once_with("encrypted-value")
        self.assertEqual(decoded["password"], "plain-auth-code")

    def test_background_smtp_settings_never_use_broken_ciphertext_as_password(self):
        stored = {"smtp": {"enabled": True, "password": "broken-ciphertext"}}
        with patch.object(task_runner, "decrypt_secret", side_effect=ValueError("bad ciphertext")):
            decoded = task_runner._decode_stored_smtp_settings(stored)

        self.assertEqual(decoded["password"], "")

    def test_config_load_preserves_exact_attendance_coordinates(self):
        payload = {
            "config": {
                "clockIn": {
                    "location": {"latitude": "24.437639", "longitude": "109.400559"}
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            config = ConfigManager(path=path)

        self.assertEqual(config.get_value("config.clockIn.location.latitude"), "24.437639")
        self.assertEqual(config.get_value("config.clockIn.location.longitude"), "109.400559")

    def test_create_alipay_verification_extracts_safe_registration(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={"code": 200, "msg": "success", "data": dict(SAFE_REGISTRATION)}
        )

        result = client.create_alipay_clockin_verification()

        self.assertEqual(result, SAFE_REGISTRATION)
        path, headers, payload = client._post_request.call_args.args
        self.assertEqual(path, "usercenter/alipay/v1/createAxdjk")
        self.assertEqual(headers["authorization"], "test-token")
        self.assertEqual(
            headers["client_id"],
            ApiClient.ALIPAY_VERIFICATION_CLIENT_ID,
        )
        self.assertEqual(set(payload), {"t"})
        self.assertIsInstance(payload["t"], str)
        self.assertTrue(payload["t"])

    def test_create_alipay_verification_rejects_non_alipay_scheme(self):
        client = build_api_client()
        unsafe_url = "https://example.test/verify?secret=hidden"
        client._post_request = Mock(
            return_value={
                "code": 200,
                "msg": "success",
                "data": {
                    "outRegisterNo": SAFE_REGISTRATION["outRegisterNo"],
                    "registerUrl": unsafe_url,
                },
            }
        )

        with self.assertRaisesRegex(ValueError, "支付宝安全验证链接无效") as ctx:
            client.create_alipay_clockin_verification()

        self.assertNotIn(unsafe_url, str(ctx.exception))

    def test_create_alipay_verification_rejects_non_hierarchical_alipay_url(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={
                "code": 200,
                "msg": "success",
                "data": {
                    "outRegisterNo": SAFE_REGISTRATION["outRegisterNo"],
                    "registerUrl": "alipays:platformapi/startapp?appId=test",
                },
            }
        )

        with self.assertRaisesRegex(ValueError, "支付宝安全验证链接无效"):
            client.create_alipay_clockin_verification()

    def test_create_alipay_verification_rejects_incomplete_response(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={
                "code": 200,
                "msg": "success",
                "data": {"outRegisterNo": SAFE_REGISTRATION["outRegisterNo"]},
            }
        )

        with self.assertRaisesRegex(ValueError, "支付宝安全验证响应不完整"):
            client.create_alipay_clockin_verification()

    def test_create_alipay_verification_rejects_unsafe_registration_number(self):
        for value in ("bad value", "bad/value", "x" * 129):
            with self.subTest(value=value):
                client = build_api_client()
                client._post_request = Mock(
                    return_value={
                        "code": 200,
                        "msg": "success",
                        "data": {
                            "outRegisterNo": value,
                            "registerUrl": SAFE_REGISTRATION["registerUrl"],
                        },
                    }
                )

                with self.assertRaisesRegex(
                    ValueError,
                    "支付宝安全验证登记编号无效",
                ):
                    client.create_alipay_clockin_verification()

    def test_query_alipay_verification_uses_official_endpoint(self):
        client = build_api_client()
        expected = {"code": 200, "msg": "success", "data": True}
        client._post_request = Mock(return_value=expected)

        result = client.query_alipay_clockin_verification(
            SAFE_REGISTRATION["outRegisterNo"]
        )

        self.assertEqual(result, expected)
        path, headers, payload = client._post_request.call_args.args
        self.assertEqual(path, "usercenter/alipay/v1/queryAxdj")
        self.assertEqual(headers["authorization"], "test-token")
        self.assertEqual(
            headers["client_id"],
            ApiClient.ALIPAY_VERIFICATION_CLIENT_ID,
        )
        self.assertEqual(
            payload,
            {"outRegisterNo": SAFE_REGISTRATION["outRegisterNo"]},
        )

    def test_query_alipay_verification_rejects_unsafe_registration_number(self):
        client = build_api_client()
        client._post_request = Mock()

        with self.assertRaisesRegex(ValueError, "支付宝安全验证登记编号无效"):
            client.query_alipay_clockin_verification("bad/value")

        client._post_request.assert_not_called()

    def test_initial_304_reports_verification_without_creating_registration(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={
                "code": 200,
                "msg": "304",
                "data": {"attendanceId": "attendance-304"},
            }
        )
        client.create_alipay_clockin_verification = Mock(return_value=dict(SAFE_REGISTRATION))

        result = client.submit_clock_in(build_checkin_info())

        self.assertEqual(
            result,
            {
                "status": "verification_required",
                "attendanceId": "attendance-304",
            },
        )
        client._post_request.assert_called_once()
        client.create_alipay_clockin_verification.assert_not_called()
        submitted_payload = client._post_request.call_args.args[2]
        self.assertIsNone(submitted_payload["outRegisterNo"])

    def test_303_builds_official_alipay_face_url_without_reporting_success(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={
                "code": 200,
                "msg": "303",
                "data": {"alipayToken": "face-token-123"},
            }
        )

        result = client.submit_clock_in(build_checkin_info())

        self.assertEqual(result["status"], "face_verification_required")
        self.assertTrue(
            result["registerUrl"].startswith(
                "alipays://platformapi/startapp?appId=2021006127602453"
            )
        )
        self.assertIn("alipayToken%3Dface-token-123", result["registerUrl"])
        self.assertNotIn("alipayToken", result)

    def test_continue_304_reports_verification_without_retrying_clockin(self):
        client = build_api_client()
        client._post_request = Mock(return_value={"code": 200, "msg": "304", "data": "verify"})
        refreshed_registration = {
            "outRegisterNo": "test-456-EfGh",
            "registerUrl": "alipays://platformapi/startapp?appId=refreshed",
        }
        client.create_alipay_clockin_verification = Mock(
            return_value=refreshed_registration
        )
        checkin_info = build_checkin_info()
        checkin_info["outRegisterNo"] = SAFE_REGISTRATION["outRegisterNo"]

        result = client.submit_clock_in(checkin_info)

        self.assertEqual(result, {"status": "verification_required"})
        client._post_request.assert_called_once()
        self.assertEqual(
            client._post_request.call_args.args[2]["outRegisterNo"],
            SAFE_REGISTRATION["outRegisterNo"],
        )
        client.create_alipay_clockin_verification.assert_not_called()

    def test_non_200_clockin_business_response_is_not_success(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={"code": 6111, "msg": "clock-in verification failed", "data": None}
        )

        with self.assertRaisesRegex(ValueError, "clock-in verification failed"):
            client.submit_clock_in(build_checkin_info())

    def test_code_200_non_risk_message_follows_official_success_branch(self):
        client = build_api_client()
        client._post_request = Mock(
            return_value={"code": 200, "msg": "签到成功", "data": None}
        )

        self.assertEqual(client.submit_clock_in(build_checkin_info()), {"status": "success"})

    def test_behavior_captcha_still_retries_clockin_once(self):
        client = build_api_client()
        client._post_request = Mock(
            side_effect=[
                {"code": 200, "msg": "302", "data": "captcha"},
                {"code": 200, "msg": "success", "data": "ok"},
            ]
        )
        client.solve_click_word_captcha = Mock(return_value="test-captcha")

        result = client.submit_clock_in(build_checkin_info())

        self.assertEqual(result, {"status": "success"})
        self.assertEqual(client._post_request.call_count, 2)
        self.assertEqual(
            client._post_request.call_args_list[1].args[2]["captcha"],
            "test-captcha",
        )
        client.solve_click_word_captcha.assert_called_once_with()

    def test_continue_clockin_submits_out_register_number_once(self):
        client = build_api_client()
        client._post_request = Mock(return_value={"code": 200, "msg": "success", "data": "ok"})
        checkin_info = build_checkin_info()
        checkin_info["outRegisterNo"] = SAFE_REGISTRATION["outRegisterNo"]

        result = client.submit_clock_in(checkin_info)

        self.assertEqual(result, {"status": "success"})
        client._post_request.assert_called_once()
        submitted_payload = client._post_request.call_args.args[2]
        self.assertEqual(submitted_payload["outRegisterNo"], SAFE_REGISTRATION["outRegisterNo"])
        self.assertEqual(submitted_payload["isFirstSignInWeb"], 0)
        self.assertRegex(submitted_payload["appUuid"], r"^[0-9a-f]{32}$")


class ClockInTaskResultTest(unittest.TestCase):
    def test_303_maps_to_manual_face_verification_instead_of_success(self):
        api_client = build_task_api_client(
            {
                "status": "face_verification_required",
                "registerUrl": "alipays://platformapi/startapp?appId=2021006127602453",
            }
        )

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="START",
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["details"]["verification_type"], "face")
        self.assertIn("2021006127602453", result["details"]["registerUrl"])
        api_client.create_alipay_clockin_verification.assert_not_called()

    def test_perform_clockin_maps_verification_to_fail_details(self):
        api_client = build_task_api_client(
            {"status": "verification_required", **SAFE_REGISTRATION}
        )

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="START",
            )

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["task_type"], "打卡")
        self.assertIn("支付宝安全验证", result["message"])
        self.assertEqual(result["details"]["target_type"], "START")
        self.assertEqual(
            result["details"]["outRegisterNo"],
            SAFE_REGISTRATION["outRegisterNo"],
        )
        self.assertEqual(result["details"]["registerUrl"], SAFE_REGISTRATION["registerUrl"])
        api_client.create_alipay_clockin_verification.assert_called_once_with()

    def test_replace_verification_is_not_reported_as_success_or_continuable(self):
        api_client = build_task_api_client(
            {"status": "verification_required", **SAFE_REGISTRATION},
            replace=True,
        )

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="START",
                replace=True,
            )

        self.assertEqual(result["status"], "fail")
        self.assertNotIn("outRegisterNo", result["details"])
        self.assertNotIn("registerUrl", result["details"])

    def test_continue_clockin_passes_registration_to_new_payload(self):
        api_client = build_task_api_client({"status": "success"})

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="END",
                out_register_no=SAFE_REGISTRATION["outRegisterNo"],
            )

        self.assertEqual(result["status"], "success")
        api_client.submit_clock_in.assert_called_once()
        submitted_checkin_info = api_client.submit_clock_in.call_args.args[0]
        self.assertEqual(
            submitted_checkin_info["outRegisterNo"],
            SAFE_REGISTRATION["outRegisterNo"],
        )

    def test_stored_preauthorization_is_not_injected_into_first_request(self):
        api_client = build_task_api_client({"status": "success"})
        hooks = Mock()
        hooks.claim.return_value = SimpleNamespace(id=17, out_register_no="stored-register-1")

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="START",
                target_time=task_runner.datetime(2026, 7, 16, 8, 30),
                preauthorization_hooks=hooks,
            )

        self.assertEqual(result["status"], "success")
        api_client.submit_clock_in.assert_called_once()
        first_payload = api_client.submit_clock_in.call_args.args[0]
        self.assertNotIn("outRegisterNo", first_payload)
        hooks.claim.assert_not_called()
        hooks.require_reauthorization.assert_not_called()
        api_client.create_alipay_clockin_verification.assert_not_called()

    def test_304_creates_transaction_registration_without_claiming_stored_token(self):
        api_client = build_task_api_client({"status": "verification_required"})
        hooks = Mock()
        hooks.claim.return_value = SimpleNamespace(id=18, out_register_no="stored-register-2")

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="END",
                target_time=task_runner.datetime(2026, 7, 16, 18, 30),
                preauthorization_hooks=hooks,
            )

        self.assertEqual(result["status"], "fail")
        api_client.submit_clock_in.assert_called_once()
        hooks.claim.assert_not_called()
        hooks.require_reauthorization.assert_not_called()
        api_client.create_alipay_clockin_verification.assert_called_once_with()
        self.assertEqual(result["details"]["outRegisterNo"], SAFE_REGISTRATION["outRegisterNo"])
        self.assertEqual(result["details"]["registerUrl"], SAFE_REGISTRATION["registerUrl"])

    def test_makeup_does_not_reuse_shared_day_authorization(self):
        api_client = build_task_api_client(
            {"status": "success"},
            replace=True,
        )
        hooks = Mock()
        hooks.claim.return_value = SimpleNamespace(id=19, out_register_no="makeup-register-1")

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="END",
                target_time=task_runner.datetime(2026, 7, 14, 18, 30),
                replace=True,
                preauthorization_hooks=hooks,
            )

        self.assertEqual(result["status"], "success")
        hooks.claim.assert_not_called()
        api_client.submit_clock_in_replace.assert_called_once()
        first_payload = api_client.submit_clock_in_replace.call_args.args[0]
        self.assertNotIn("outRegisterNo", first_payload)
        api_client.create_alipay_clockin_verification.assert_not_called()

    def test_submit_exception_does_not_consume_stored_preauthorization(self):
        api_client = build_task_api_client({"status": "success"})
        api_client.submit_clock_in.side_effect = RuntimeError("network timeout")
        hooks = Mock()
        hooks.claim.return_value = SimpleNamespace(
            id=20, out_register_no="stored-register-3"
        )

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="START",
                target_time=task_runner.datetime(2026, 7, 16, 8, 30),
                preauthorization_hooks=hooks,
            )

        self.assertEqual(result["status"], "fail")
        hooks.claim.assert_not_called()
        hooks.require_reauthorization.assert_not_called()

    def test_explicit_continue_does_not_claim_preauthorization(self):
        api_client = build_task_api_client({"status": "success"})
        hooks = Mock()

        with patch.object(task_runner, "upload_img", return_value=[]):
            result = task_runner.perform_clock_in(
                api_client,
                build_task_config(),
                forced_checkin_type="START",
                out_register_no=SAFE_REGISTRATION["outRegisterNo"],
                preauthorization_hooks=hooks,
            )

        self.assertEqual(result["status"], "success")
        hooks.claim.assert_not_called()


class FakeRequest:
    headers = {}
    client = SimpleNamespace(host="127.0.0.1")


class AlipayContinueApiTest(unittest.TestCase):
    def test_admin_run_idempotency_record_does_not_persist_verification_details(self):
        user = User(
            id=10,
            tenant_id="acme",
            phone="test-user",
            password="test-password",
        )
        pending_result = {
            "status": "fail",
            "message": "需要完成支付宝安全验证",
            "task_type": "打卡",
            "details": {"target_type": "START", **SAFE_REGISTRATION},
        }
        request = SimpleNamespace(
            headers={"Idempotency-Key": "test-alipay-verification"},
            client=SimpleNamespace(host="127.0.0.1"),
        )
        session = Mock()

        with (
            patch.object(api, "_manual_operation_existing_response", return_value=None),
            patch.object(api, "claim_idempotency_record", return_value=None),
            patch.object(api, "_rate_limit"),
            patch.object(api, "_get_active_user_for_payload", return_value=user),
            patch.object(api, "user_to_config", return_value={"config": {}}),
            patch.object(api, "run_task_by_config", return_value=[pending_result]),
            patch.object(api, "apply_execution_results_to_user", return_value="Fail"),
            patch.object(api, "finalize_idempotency_record") as finalize,
        ):
            response = api.run_user_task(
                request=request,
                session=session,
                user_id=10,
                req=api.AppRunRequest(task_type="clock_in"),
                operator={"sub": "operator", "tenant_id": "acme"},
            )

        self.assertEqual(
            response["results"][0]["details"]["outRegisterNo"],
            SAFE_REGISTRATION["outRegisterNo"],
        )
        stored_response = finalize.call_args.kwargs["response"]
        self.assertEqual(
            stored_response["results"][0]["details"],
            {"target_type": "START"},
        )

    def test_verification_details_are_not_in_message_push_content(self):
        pending_result = {
            "status": "fail",
            "message": "需要完成支付宝安全验证",
            "task_type": "打卡",
            "details": {
                "target_type": "START",
                **SAFE_REGISTRATION,
            },
        }

        markdown = MessagePusher._generate_markdown_message([pending_result])
        html = MessagePusher._generate_html_message([pending_result])

        for content in (markdown, html):
            self.assertNotIn(SAFE_REGISTRATION["outRegisterNo"], content)
            self.assertNotIn(SAFE_REGISTRATION["registerUrl"], content)
            self.assertIn("target_type", content)

    def test_verification_details_are_not_persisted(self):
        user = User(phone="test-user", password="test-password")
        pending_result = {
            "status": "fail",
            "message": "需要完成支付宝安全验证，请验证后继续打卡",
            "task_type": "打卡",
            "details": {
                "target_type": "START",
                **SAFE_REGISTRATION,
            },
        }

        apply_execution_results_to_user(
            user,
            [pending_result],
            {"config": {}, "userInfo": {}, "planInfo": {}},
        )

        stored_details = user.last_execution_result[0]["details"]
        self.assertEqual(stored_details, {"target_type": "START"})
        self.assertEqual(pending_result["details"]["outRegisterNo"], SAFE_REGISTRATION["outRegisterNo"])
        self.assertEqual(pending_result["details"]["registerUrl"], SAFE_REGISTRATION["registerUrl"])

    def test_continue_request_validates_registration_number_and_target_type(self):
        valid = api.AlipayClockInContinueRequest(
            out_register_no=SAFE_REGISTRATION["outRegisterNo"],
            target_type="end",
        )
        self.assertEqual(
            api._alipay_continue_values(valid),
            (SAFE_REGISTRATION["outRegisterNo"], "END", "account"),
        )

        face = api.AlipayClockInContinueRequest(
            target_type="START",
            verification_type="face",
        )
        self.assertEqual(api._alipay_continue_values(face), ("", "START", "face"))

        invalid_values = ["", "bad value", "bad/value", "x" * 129]
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(HTTPException) as ctx:
                    api._alipay_continue_values(
                        api.AlipayClockInContinueRequest(
                            out_register_no=value,
                            target_type="START",
                        )
                    )
                self.assertEqual(ctx.exception.status_code, 400)

        with self.assertRaises(HTTPException) as ctx:
            api._alipay_continue_values(
                api.AlipayClockInContinueRequest(
                    out_register_no=SAFE_REGISTRATION["outRegisterNo"],
                    target_type="HOLIDAY",
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_continue_business_queries_registration_and_confirms_server_record(self):
        user = User(id=7, phone="test-user", password="test-password")
        config_data = {"config": {}, "userInfo": {}, "planInfo": {}}
        today = api.datetime.datetime.now(api.BEIJING_TZ).date().isoformat()

        with (
            patch.object(api, "user_to_config", return_value=config_data),
            patch.object(api, "ApiClient") as api_client_type,
            patch.object(api, "_ensure_remote_runtime") as ensure_runtime,
            patch.object(api, "apply_execution_results_to_user") as apply_results,
        ):
            api_client_type.return_value.query_alipay_clockin_verification.return_value = {
                "code": 200,
                "msg": "success",
            }
            api_client_type.return_value.get_checkin_records.return_value = [
                {"type": "START", "attendenceTime": f"{today} 08:30:00"}
            ]
            result, returned_config = api._continue_alipay_clockin_for_user(
                user,
                SAFE_REGISTRATION["outRegisterNo"],
                "START",
            )

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["details"]["verification_confirmed"])
        self.assertTrue(result["details"]["record_confirmed"])
        self.assertIs(returned_config, config_data)
        ensure_runtime.assert_called_once()
        api_client_type.return_value.query_alipay_clockin_verification.assert_called_once_with(
            SAFE_REGISTRATION["outRegisterNo"],
        )
        api_client_type.return_value.get_checkin_records.assert_called_once_with()
        apply_results.assert_called_once_with(user, [result], config_data)
        self.assertIs(ensure_runtime.call_args.args[0], api_client_type.return_value)

    def test_face_continue_only_refreshes_record_without_query_axdj(self):
        user = User(id=9, phone="test-user", password="test-password")
        config_data = {"config": {}, "userInfo": {}, "planInfo": {}}
        today = api.datetime.datetime.now(api.BEIJING_TZ).date().isoformat()

        with (
            patch.object(api, "user_to_config", return_value=config_data),
            patch.object(api, "ApiClient") as api_client_type,
            patch.object(api, "_ensure_remote_runtime"),
            patch.object(api, "apply_execution_results_to_user"),
        ):
            api_client_type.return_value.get_checkin_records.return_value = [
                {"type": "END", "attendenceTime": f"{today} 18:30:00"}
            ]
            result, _ = api._continue_alipay_clockin_for_user(
                user,
                "",
                "END",
                "face",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["details"]["verification_type"], "face")
        api_client_type.return_value.query_alipay_clockin_verification.assert_not_called()
        api_client_type.return_value.get_checkin_records.assert_called_once_with()

    def test_continue_retries_record_refresh_for_eventual_consistency(self):
        user = User(id=11, phone="test-user", password="test-password")
        config_data = {"config": {}, "userInfo": {}, "planInfo": {}}
        today = api.datetime.datetime.now(api.BEIJING_TZ).date().isoformat()

        with (
            patch.object(api, "user_to_config", return_value=config_data),
            patch.object(api, "ApiClient") as api_client_type,
            patch.object(api, "_ensure_remote_runtime"),
            patch.object(api, "apply_execution_results_to_user"),
            patch.object(api.time, "sleep") as sleep,
        ):
            api_client_type.return_value.get_checkin_records.side_effect = [
                [],
                [],
                [{"type": "START", "attendenceTime": f"{today} 08:30:00"}],
            ]
            result, _ = api._continue_alipay_clockin_for_user(
                user,
                SAFE_REGISTRATION["outRegisterNo"],
                "START",
                "account",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(api_client_type.return_value.get_checkin_records.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_continue_routes_are_registered_with_admin_permission(self):
        routes = {getattr(route, "path", ""): route for route in api.router.routes}
        self.assertIn("/app/clock-in/alipay/continue", routes)
        admin_route = routes["/users/{user_id}/clock-in/alipay/continue"]
        dependency_calls = {
            dependency.call for dependency in admin_route.dependant.dependencies
        }
        self.assertIn(api.require_tasks_run, dependency_calls)

    def test_app_continue_uses_bound_user_limit_and_sanitized_audit(self):
        user = User(
            id=8,
            tenant_id="acme",
            phone="test-user",
            password="test-password",
        )
        request_model = api.AlipayClockInContinueRequest(
            out_register_no=SAFE_REGISTRATION["outRegisterNo"],
            target_type="START",
        )
        session = Mock()
        pending_result = {
            "status": "fail",
            "message": "需要完成支付宝安全验证，请验证后继续打卡",
            "task_type": "打卡",
            "details": dict(SAFE_REGISTRATION),
        }

        with (
            patch.object(api, "_get_authed_app_user", return_value=Mock()),
            patch.object(api, "_get_bound_task_user", return_value=user),
            patch.object(api, "_rate_limit") as rate_limit,
            patch.object(
                api,
                "_continue_alipay_clockin_for_user",
                return_value=(pending_result, {"config": {}}),
            ) as continue_clockin,
        ):
            response = api.app_continue_alipay_clockin(
                request=FakeRequest(),
                req=request_model,
                session=session,
                payload={"sub": "app:1", "tenant_id": "acme"},
            )

        self.assertEqual(response, {"result": pending_result})
        rate_limit.assert_called_once_with(
            "app_run:127.0.0.1:8",
            limit=3,
            per_seconds=60,
        )
        continue_clockin.assert_called_once_with(
            user,
            SAFE_REGISTRATION["outRegisterNo"],
            "START",
            "account",
            api.datetime.datetime.now(api.BEIJING_TZ).date().isoformat(),
        )
        audit = next(
            call.args[0]
            for call in session.add.call_args_list
            if isinstance(call.args[0], AuditLog)
        )
        self.assertEqual(audit.detail, {"status": "fail", "target_type": "START"})
        self.assertNotIn(SAFE_REGISTRATION["outRegisterNo"], str(audit.detail))
        self.assertNotIn(SAFE_REGISTRATION["registerUrl"], str(audit.detail))
        session.commit.assert_called_once_with()

    def test_admin_continue_uses_tenant_scope_limit_and_sanitized_audit(self):
        user = User(
            id=9,
            tenant_id="acme",
            phone="test-user",
            password="test-password",
        )
        request_model = api.AlipayClockInContinueRequest(
            out_register_no=SAFE_REGISTRATION["outRegisterNo"],
            target_type="END",
        )
        session = Mock()
        success_result = {
            "status": "success",
            "message": "下班打卡成功",
            "task_type": "打卡",
            "details": {},
        }
        operator = {"sub": "operator", "tenant_id": "acme"}

        with (
            patch.object(api, "_get_active_user_for_payload", return_value=user) as get_user,
            patch.object(api, "_rate_limit") as rate_limit,
            patch.object(
                api,
                "_continue_alipay_clockin_for_user",
                return_value=(success_result, {"config": {}}),
            ),
        ):
            response = api.continue_user_alipay_clockin(
                request=FakeRequest(),
                req=request_model,
                session=session,
                user_id=9,
                operator=operator,
            )

        self.assertEqual(response, {"result": success_result})
        get_user.assert_called_once_with(session, 9, operator)
        rate_limit.assert_called_once_with(
            "run:127.0.0.1:9",
            limit=2,
            per_seconds=60,
        )
        audit = next(
            call.args[0]
            for call in session.add.call_args_list
            if isinstance(call.args[0], AuditLog)
        )
        self.assertEqual(audit.detail, {"status": "success", "target_type": "END"})
        self.assertNotIn(SAFE_REGISTRATION["outRegisterNo"], str(audit.detail))
        session.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
