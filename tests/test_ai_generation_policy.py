import socket
import threading
import unittest
import importlib
from unittest.mock import patch

from server.coreApi.AiServiceClient import _ai_endpoint_detail, _validate_ai_endpoint_policy, generate_article


class FakeAIResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "Generated weekly report content."}}]}


class FakeConfig:
    def get_value(self, key):
        values = {
            "config.ai.apikey": "test-key",
            "config.ai.apiUrl": "https://api.example.com",
            "config.ai.model": "test-model",
            "userInfo.orgJson.majorName": "Computer Science",
        }
        return values.get(key)


class BlockedModelConfig(FakeConfig):
    def get_value(self, key):
        if key == "config.ai.model":
            return "blocked-model"
        return super().get_value(key)


class AIGenerationPolicyTest(unittest.TestCase):
    def test_private_url_is_rejected_by_default(self):
        with patch.dict("os.environ", {"AI_ALLOWED_HOSTS": "", "ALLOW_PRIVATE_AI_ENDPOINTS": ""}, clear=False):
            with self.assertRaises(ValueError):
                _validate_ai_endpoint_policy("http://127.0.0.1:8080/v1/chat/completions")

    def test_private_url_requires_explicit_opt_in_and_allowlist(self):
        with patch.dict(
            "os.environ",
            {
                "ALLOW_PRIVATE_AI_ENDPOINTS": "true",
                "AI_ALLOWED_HOSTS": "127.0.0.1,ai.internal",
            },
            clear=False,
        ):
            detail = _validate_ai_endpoint_policy("http://127.0.0.1:8080/v1/chat/completions")

        self.assertEqual(detail["host"], "127.0.0.1")

    def test_allowlist_blocks_unlisted_host_without_special_casing_private_ips(self):
        with patch.dict("os.environ", {"ALLOW_PRIVATE_AI_ENDPOINTS": "true", "AI_ALLOWED_HOSTS": "127.0.0.1,ai.internal"}, clear=False):
            with self.assertRaises(ValueError):
                _validate_ai_endpoint_policy("http://192.168.1.20:8080/v1/chat/completions")

    def test_endpoint_detail_never_contains_api_key(self):
        detail = _ai_endpoint_detail("http://user:secret@127.0.0.1:8080/v1/chat/completions")

        self.assertEqual(detail["host"], "127.0.0.1")
        self.assertNotIn("secret", str(detail))

    def test_model_allowlist_blocks_unapproved_model(self):
        with patch.dict(
            "os.environ",
            {"AI_ALLOWED_MODELS": "approved-model", "AI_ALLOWED_HOSTS": "", "ALLOW_PRIVATE_AI_ENDPOINTS": ""},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                generate_article(BlockedModelConfig(), "weekly report", {"practiceCompanyEntity": {}}, count=50)

    def test_generate_article_pins_validated_dns_and_uses_short_timeout(self):
        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", int(port)))]

        def fake_post(url, **kwargs):
            self.assertEqual(url, "https://api.example.com/v1/chat/completions")
            self.assertLessEqual(kwargs["timeout"], 60)
            self.assertIn("Prompt-Version:", kwargs["json"]["messages"][0]["content"])
            resolved = socket.getaddrinfo("api.example.com", 443, type=socket.SOCK_STREAM)
            self.assertEqual(resolved[0][4][0], "93.184.216.34")
            return FakeAIResponse()

        with (
            patch.dict("os.environ", {"AI_ALLOWED_HOSTS": "", "ALLOW_PRIVATE_AI_ENDPOINTS": ""}, clear=False),
            patch("server.coreApi.AiServiceClient.socket.getaddrinfo", side_effect=fake_getaddrinfo),
            patch("server.coreApi.AiServiceClient.requests.post", side_effect=fake_post),
        ):
            content = generate_article(FakeConfig(), "weekly report", {"practiceCompanyEntity": {}}, count=50)

        self.assertIn("Generated weekly report", content)

    def test_dns_pin_does_not_leak_across_threads(self):
        from server.coreApi import AiServiceClient as client_module

        pinned_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        fallback_infos = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("198.51.100.10", 443))]
        barrier = threading.Barrier(2)
        worker_ready = threading.Event()
        worker_result = {}

        def fake_original(host, port, *args, **kwargs):
            return fallback_infos if host == "api.example.com" else []

        def worker():
            barrier.wait()
            worker_result["infos"] = socket.getaddrinfo("api.example.com", 443, type=socket.SOCK_STREAM)
            worker_ready.set()

        with patch.object(client_module, "_ORIGINAL_GETADDRINFO", side_effect=fake_original):
            thread = threading.Thread(target=worker)
            thread.start()
            with client_module._pin_getaddrinfo("api.example.com", 443, pinned_infos):
                barrier.wait()
                main_result = socket.getaddrinfo("api.example.com", 443, type=socket.SOCK_STREAM)
                self.assertTrue(worker_ready.wait(timeout=5))
            thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(main_result[0][4][0], "93.184.216.34")
        self.assertEqual(worker_result["infos"][0][4][0], "198.51.100.10")

    def test_import_does_not_patch_socket_getaddrinfo(self):
        from server.coreApi import AiServiceClient as client_module

        original = socket.getaddrinfo
        try:
            importlib.reload(client_module)
            self.assertIs(socket.getaddrinfo, original)
        finally:
            socket.getaddrinfo = original


if __name__ == "__main__":
    unittest.main()
