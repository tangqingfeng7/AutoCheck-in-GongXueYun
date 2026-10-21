import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from server import api
from server.auth import hash_password
from server.models import AdminUser


def _model_fields(model) -> set[str]:
    return set(getattr(model, "model_fields", None) or getattr(model, "__fields__", {}))


class AdminMfaRemovalTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        self.request = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.10"))
        self.response = SimpleNamespace(headers={}, set_cookie=lambda *args, **kwargs: None)

    def test_admin_login_request_no_longer_accepts_mfa_code(self):
        self.assertNotIn("mfa_code", _model_fields(api.LoginRequest))
        self.assertNotIn("mfa_enabled", _model_fields(AdminUser))
        self.assertNotIn("mfa_totp_secret", _model_fields(AdminUser))
        self.assertNotIn("mfa_confirmed_at", _model_fields(AdminUser))
        self.assertFalse(any(route.path.startswith("/auth/mfa") for route in api.router.routes))
        self.assertFalse(hasattr(api, "MfaCodeRequest"))
        self.assertFalse(hasattr(api, "MfaSetupRequest"))
        self.assertFalse(hasattr(api, "MfaDisableRequest"))

    def test_legacy_mfa_columns_do_not_block_password_login(self):
        with Session(self.engine) as session:
            session.exec(text("ALTER TABLE adminuser ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT 0"))
            session.exec(text("ALTER TABLE adminuser ADD COLUMN mfa_totp_secret TEXT NULL"))
            session.add(AdminUser(username="admin", password_hash=hash_password("correct-password-123"), role="admin"))
            session.flush()
            session.exec(
                text("UPDATE adminuser SET mfa_enabled = 1, mfa_totp_secret = 'legacy-secret' WHERE username = 'admin'")
            )
            session.commit()

        with (
            patch("server.api.engine", self.engine),
            patch("server.api._rate_limit", lambda *args, **kwargs: None),
            patch.dict("os.environ", {"APP_SECRET": "test-secret-value-with-more-than-thirty-two-chars"}, clear=False),
        ):
            result = api.admin_login(
                request=self.request,
                response=self.response,
                req=api.LoginRequest(username="admin", password="correct-password-123"),
            )

        self.assertEqual(result["role"], "admin")


if __name__ == "__main__":
    unittest.main()
