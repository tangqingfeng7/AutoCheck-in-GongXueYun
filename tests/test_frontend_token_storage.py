import unittest
from pathlib import Path


class FrontendTokenStorageTest(unittest.TestCase):
    def test_auth_tokens_are_not_read_from_local_storage(self):
        root = Path(__file__).resolve().parents[1]
        files = [
            root / "web" / "src" / "stores" / "auth.js",
            root / "web" / "src" / "stores" / "userAuth.js",
            root / "web" / "src" / "api" / "http.js",
        ]

        combined = "\n".join(path.read_text(encoding="utf-8") for path in files)

        self.assertNotIn("localStorage.getItem", combined)
        self.assertNotIn("localStorage.setItem", combined)


if __name__ == "__main__":
    unittest.main()
