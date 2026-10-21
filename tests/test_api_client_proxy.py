import unittest
import socket
from unittest.mock import Mock, patch

import requests

from server.coreApi.MainLogicApi import ApiClient
from server.util.Config import ConfigManager


class FakeResponse:
    def __init__(self, payload, text=""):
        self._payload = payload
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class ApiClientProxyTest(unittest.TestCase):
    def test_post_request_does_not_use_proxy_until_explicitly_enabled(self):
        with patch.dict("os.environ", {"MOGUDING_PROXY_URLS": "http://proxy-a.example:8080"}, clear=False):
            client = ApiClient(ConfigManager(config={}))
            client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

            result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        self.assertNotIn("proxies", client.session.post.call_args.kwargs)

    def test_post_request_uses_configured_proxy_after_enable_proxy(self):
        with patch.dict("os.environ", {"MOGUDING_PROXY_URLS": "http://proxy-a.example:8080"}, clear=False):
            client = ApiClient(ConfigManager(config={}))
            client.enable_proxy()
            client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

            result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        proxies = client.session.post.call_args.kwargs["proxies"]
        self.assertEqual(
            proxies,
            {
                "http": "http://proxy-a.example:8080",
                "https": "http://proxy-a.example:8080",
            },
        )

    def test_post_request_rotates_proxy_after_rate_limit_response(self):
        with patch.dict(
            "os.environ",
            {"MOGUDING_PROXY_URLS": "http://proxy-a.example:8080,http://proxy-b.example:8080"},
            clear=False,
        ):
            client = ApiClient(ConfigManager(config={}))
            client.enable_proxy()
            client.max_retries = 2
            client.session.post = Mock(
                side_effect=[
                    FakeResponse({"code": 500, "msg": "IP请求过于频繁，请稍后再试"}),
                    FakeResponse({"code": 200, "msg": "ok"}),
                ]
            )

            with patch("server.coreApi.MainLogicApi.time.sleep") as sleep:
                result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        calls = client.session.post.call_args_list
        self.assertEqual(calls[0].kwargs["proxies"]["https"], "http://proxy-a.example:8080")
        self.assertEqual(calls[1].kwargs["proxies"]["https"], "http://proxy-b.example:8080")
        sleep.assert_called_once()

    @patch("server.coreApi.MainLogicApi.socket.getaddrinfo", return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))])
    def test_post_request_fetches_proxy_from_api_and_adds_credentials(self, resolve):
        proxy_api = (
            "http://capi.51daili.com/traffic/getip?"
            "linePoolIndex=1&packid=12&time=2&qty=1&port=1&format=txt&"
            "accessName=proxyUser&accessPassword=proxyPass"
        )
        with patch.dict("os.environ", {"MOGUDING_PROXY_API_URL": proxy_api}, clear=False):
            with patch("server.coreApi.MainLogicApi.requests.get", return_value=FakeResponse({}, text="1.2.3.4:5678\n")) as get:
                client = ApiClient(ConfigManager(config={}))
                client.enable_proxy()
                client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

                result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        get.assert_called_once_with(proxy_api, timeout=10.0)
        proxies = client.session.post.call_args.kwargs["proxies"]
        self.assertEqual(
            proxies,
            {
                "http": "http://proxyUser:proxyPass@1.2.3.4:5678",
                "https": "http://proxyUser:proxyPass@1.2.3.4:5678",
            },
        )

    def test_proxy_fetch_api_rejects_private_endpoint_by_default(self):
        proxy_api = "http://127.0.0.1:8080/getip?accessName=proxyUser&accessPassword=proxyPass"
        with patch.dict(
            "os.environ",
            {
                "MOGUDING_PROXY_API_URL": proxy_api,
                "MOGUDING_PROXY_ALLOWED_HOSTS": "",
                "ALLOW_PRIVATE_MOGUDING_PROXY_ENDPOINTS": "",
            },
            clear=False,
        ):
            with patch("server.coreApi.MainLogicApi.requests.get") as get:
                client = ApiClient(ConfigManager(config={}))
                client.enable_proxy()
                client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

                result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        get.assert_not_called()
        self.assertNotIn("proxies", client.session.post.call_args.kwargs)

    def test_proxy_fetch_api_allows_private_endpoint_with_opt_in_and_allowlist(self):
        proxy_api = "http://127.0.0.1:8080/getip?accessName=proxyUser&accessPassword=proxyPass"
        with patch.dict(
            "os.environ",
            {
                "MOGUDING_PROXY_API_URL": proxy_api,
                "MOGUDING_PROXY_ALLOWED_HOSTS": "127.0.0.1",
                "ALLOW_PRIVATE_MOGUDING_PROXY_ENDPOINTS": "true",
            },
            clear=False,
        ):
            with patch("server.coreApi.MainLogicApi.requests.get", return_value=FakeResponse({}, text="1.2.3.4:5678\n")) as get:
                client = ApiClient(ConfigManager(config={}))
                client.enable_proxy()
                client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

                result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        get.assert_called_once_with(proxy_api, timeout=10.0)
        self.assertEqual(client.session.post.call_args.kwargs["proxies"]["https"], "http://proxyUser:proxyPass@1.2.3.4:5678")

    @patch("server.coreApi.MainLogicApi.socket.getaddrinfo", return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))])
    def test_post_request_refetches_proxy_from_api_after_rate_limit(self, resolve):
        proxy_api = (
            "http://capi.51daili.com/traffic/getip?"
            "format=txt&accessName=proxyUser&accessPassword=proxyPass"
        )
        with patch.dict("os.environ", {"MOGUDING_PROXY_API_URL": proxy_api}, clear=False):
            with patch(
                "server.coreApi.MainLogicApi.requests.get",
                side_effect=[
                    FakeResponse({}, text="1.2.3.4:5678\n"),
                    FakeResponse({}, text="5.6.7.8:9012\n"),
                ],
            ) as get:
                client = ApiClient(ConfigManager(config={}))
                client.enable_proxy()
                client.max_retries = 2
                client.session.post = Mock(
                    side_effect=[
                        FakeResponse({"code": 500, "msg": "IP请求过于频繁，请稍后再试"}),
                        FakeResponse({"code": 200, "msg": "ok"}),
                    ]
                )

                with patch("server.coreApi.MainLogicApi.time.sleep") as sleep:
                    result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        self.assertEqual(get.call_count, 2)
        calls = client.session.post.call_args_list
        self.assertEqual(calls[0].kwargs["proxies"]["https"], "http://proxyUser:proxyPass@1.2.3.4:5678")
        self.assertEqual(calls[1].kwargs["proxies"]["https"], "http://proxyUser:proxyPass@5.6.7.8:9012")
        sleep.assert_called_once()

    @patch("server.coreApi.MainLogicApi.socket.getaddrinfo", return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 80))])
    def test_post_request_uses_global_web_proxy_settings(self, resolve):
        proxy_api = (
            "http://capi.51daili.com/traffic/getip?"
            "format=txt&accessName=webUser&accessPassword=webPass"
        )
        env = {
            "MOGUDING_PROXY_API_URL": "",
            "MOGUDING_PROXY_FETCH_URL": "",
            "MOGUDING_PROXY_URLS": "",
            "MOGUDING_PROXY_URL": "",
            "MOGUDING_PROXY": "",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "server.coreApi.MainLogicApi.load_global_proxy_settings",
                return_value={
                    "enabled": True,
                    "apiUrl": proxy_api,
                    "ttlSeconds": 50,
                    "apiTimeoutSeconds": 8,
                    "proxyUrls": "",
                },
            ) as load_global:
                with patch("server.coreApi.MainLogicApi.requests.get", return_value=FakeResponse({}, text="9.8.7.6:5432\n")) as get:
                    client = ApiClient(ConfigManager(config={}))
                    client.enable_proxy()
                    client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

                    result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        load_global.assert_called_once()
        get.assert_called_once_with(proxy_api, timeout=8.0)
        proxies = client.session.post.call_args.kwargs["proxies"]
        self.assertEqual(proxies["https"], "http://webUser:webPass@9.8.7.6:5432")

    def test_disabled_global_web_proxy_settings_use_normal_network(self):
        env = {
            "MOGUDING_PROXY_API_URL": "",
            "MOGUDING_PROXY_FETCH_URL": "",
            "MOGUDING_PROXY_URLS": "",
            "MOGUDING_PROXY_URL": "",
            "MOGUDING_PROXY": "",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch(
                "server.coreApi.MainLogicApi.load_global_proxy_settings",
                return_value={
                    "enabled": False,
                    "apiUrl": "http://capi.example/getip?accessName=user&accessPassword=pass",
                    "ttlSeconds": 50,
                    "apiTimeoutSeconds": 8,
                    "proxyUrls": "http://proxy-a.example:8080",
                },
            ) as load_global:
                with patch("server.coreApi.MainLogicApi.requests.get") as get:
                    client = ApiClient(ConfigManager(config={}))
                    client.enable_proxy()
                    client.session.post = Mock(return_value=FakeResponse({"code": 200, "msg": "ok"}))

                    result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        load_global.assert_called_once()
        get.assert_not_called()
        self.assertNotIn("proxies", client.session.post.call_args.kwargs)

    def test_post_request_rotates_proxy_after_proxy_request_error(self):
        with patch.dict(
            "os.environ",
            {"MOGUDING_PROXY_URLS": "http://proxy-a.example:8080,http://proxy-b.example:8080"},
            clear=False,
        ):
            client = ApiClient(ConfigManager(config={}))
            client.enable_proxy()
            client.max_retries = 2
            client.session.post = Mock(
                side_effect=[
                    requests.exceptions.ProxyError("proxy unavailable"),
                    FakeResponse({"code": 200, "msg": "ok"}),
                ]
            )

            with patch("server.coreApi.MainLogicApi.time.sleep") as sleep:
                result = client._post_request("test/path", {}, {})

        self.assertEqual(result["code"], 200)
        calls = client.session.post.call_args_list
        self.assertEqual(calls[0].kwargs["proxies"]["https"], "http://proxy-a.example:8080")
        self.assertEqual(calls[1].kwargs["proxies"]["https"], "http://proxy-b.example:8080")
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
