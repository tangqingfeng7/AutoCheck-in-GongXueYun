import unittest
from unittest.mock import patch


class SecretStoreHardeningTest(unittest.TestCase):
    def test_development_without_key_keeps_legacy_plaintext_compatibility(self):
        from server.secret_store import encrypt_secret

        with patch.dict("os.environ", {"APP_ENV": "development"}, clear=True):
            self.assertEqual(encrypt_secret("plain-secret"), "plain-secret")

    def test_production_requires_secret_encryption_key_for_new_values(self):
        from server.secret_store import encrypt_secret

        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            with self.assertRaises(ValueError):
                encrypt_secret("plain-secret")


if __name__ == "__main__":
    unittest.main()
