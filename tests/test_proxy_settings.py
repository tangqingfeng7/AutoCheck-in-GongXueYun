import unittest

from server.proxy_settings import normalize_proxy_settings


class ProxySettingsTest(unittest.TestCase):
    def test_normalize_proxy_settings_keeps_expected_fields(self):
        result = normalize_proxy_settings(
            {
                "enabled": True,
                "apiUrl": " http://proxy.example/get?accessName=u&accessPassword=p ",
                "ttlSeconds": "50",
                "apiTimeoutSeconds": "8",
                "proxyUrls": "http://1.2.3.4:8080",
            }
        )

        self.assertTrue(result["enabled"])
        self.assertEqual(result["apiUrl"], "http://proxy.example/get?accessName=u&accessPassword=p")
        self.assertEqual(result["ttlSeconds"], 50.0)
        self.assertEqual(result["apiTimeoutSeconds"], 8.0)
        self.assertEqual(result["proxyUrls"], "http://1.2.3.4:8080")

    def test_normalize_proxy_settings_clamps_invalid_numbers(self):
        result = normalize_proxy_settings(
            {
                "enabled": True,
                "ttlSeconds": "-1",
                "apiTimeoutSeconds": "999",
            }
        )

        self.assertEqual(result["ttlSeconds"], 0.0)
        self.assertEqual(result["apiTimeoutSeconds"], 30.0)


if __name__ == "__main__":
    unittest.main()
