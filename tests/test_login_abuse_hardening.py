import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from server import api
from server.auth import hash_password, verify_password
from server.models import AdminUser, AppUser, AuditLog, User
from server.secret_store import encrypt_secret
from server.time_utils import utc_now


class LoginAbuseHardeningTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        self.request = SimpleNamespace(headers={}, client=SimpleNamespace(host="203.0.113.10"))
        self.response = SimpleNamespace(headers={}, set_cookie=lambda *args, **kwargs: None)

    def _patch_runtime(self):
        return (
            patch("server.api.engine", self.engine),
            patch("server.api._rate_limit", lambda *args, **kwargs: None),
            patch.dict(
                "os.environ",
                {
                    "LOGIN_LOCKOUT_FAILURES": "2",
                    "LOGIN_LOCKOUT_SECONDS": "900",
                    "APP_SECRET": "test-secret-value-with-more-than-thirty-two-chars",
                    "USER_PASSWORD_KEY": "test-user-password-key",
                },
                clear=False,
            ),
        )

    def test_admin_failed_login_is_audited_and_locks_account(self):
        with Session(self.engine) as session:
            session.add(AdminUser(username="admin", password_hash=hash_password("correct-password-123"), role="admin"))
            session.commit()

        with self._patch_runtime()[0], self._patch_runtime()[1], self._patch_runtime()[2]:
            for _ in range(2):
                with self.assertRaises(HTTPException):
                    api.admin_login(
                        request=self.request,
                        response=self.response,
                        req=api.LoginRequest(username="admin", password="wrong-password"),
                    )

        with Session(self.engine) as session:
            user = session.exec(select(AdminUser).where(AdminUser.username == "admin")).one()
            logs = session.exec(select(AuditLog).where(AuditLog.action == "auth.login.failed")).all()

        self.assertEqual(user.failed_login_count, 2)
        self.assertIsNotNone(user.locked_until)
        self.assertEqual(len(logs), 2)
        self.assertNotIn("wrong-password", str([log.detail for log in logs]))

        with self._patch_runtime()[0], self._patch_runtime()[1], self._patch_runtime()[2]:
            with self.assertRaises(HTTPException) as ctx:
                api.admin_login(
                    request=self.request,
                    response=self.response,
                    req=api.LoginRequest(username="admin", password="correct-password-123"),
                )

        self.assertEqual(ctx.exception.status_code, 423)

    def test_successful_admin_login_resets_failure_state(self):
        with Session(self.engine) as session:
            session.add(
                AdminUser(
                    username="admin",
                    password_hash=hash_password("correct-password-123"),
                    role="admin",
                    failed_login_count=1,
                    locked_until=utc_now() - datetime.timedelta(seconds=1),
                )
            )
            session.commit()

        with self._patch_runtime()[0], self._patch_runtime()[1], self._patch_runtime()[2]:
            result = api.admin_login(
                request=self.request,
                response=self.response,
                req=api.LoginRequest(username="admin", password="correct-password-123"),
            )

        with Session(self.engine) as session:
            user = session.exec(select(AdminUser).where(AdminUser.username == "admin")).one()

        self.assertEqual(result["role"], "admin")
        self.assertEqual(user.failed_login_count, 0)
        self.assertIsNone(user.locked_until)

    def test_app_failed_login_is_audited_and_locks_account(self):
        with Session(self.engine) as session:
            session.add(AppUser(phone="13800000000", password_hash=hash_password("correct-password-123")))
            session.commit()

        with self._patch_runtime()[0], self._patch_runtime()[1], self._patch_runtime()[2]:
            for _ in range(2):
                with self.assertRaises(HTTPException):
                    api.app_login(
                        request=self.request,
                        response=self.response,
                        req=api.AppLoginRequest(phone="13800000000", password="wrong-password"),
                    )

        with Session(self.engine) as session:
            user = session.exec(select(AppUser).where(AppUser.phone == "13800000000")).one()
            logs = session.exec(select(AuditLog).where(AuditLog.action == "app.login.failed")).all()

        self.assertEqual(user.failed_login_count, 2)
        self.assertIsNotNone(user.locked_until)
        self.assertEqual(len(logs), 2)

    def test_app_login_accepts_admin_created_user_password(self):
        patches = self._patch_runtime()
        with patches[0], patches[1], patches[2]:
            with Session(self.engine) as session:
                user = User(
                    phone="13900000000",
                    password=encrypt_secret("correct-password-123"),
                    app_enabled=True,
                    enable_clockin=False,
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                user_id = user.id

            result = api.app_login(
                request=self.request,
                response=self.response,
                req=api.AppLoginRequest(phone="13900000000", password="correct-password-123"),
            )

        with Session(self.engine) as session:
            app_user = session.exec(select(AppUser).where(AppUser.phone == "13900000000")).one()

        self.assertEqual(result["phone"], "13900000000")
        self.assertEqual(app_user.bound_user_id, user_id)
        self.assertTrue(app_user.enabled)

    def test_app_login_syncs_existing_app_user_from_legacy_user_password(self):
        patches = self._patch_runtime()
        with patches[0], patches[1], patches[2]:
            with Session(self.engine) as session:
                user = User(
                    phone="13900000001",
                    password=encrypt_secret("correct-password-123"),
                    app_enabled=True,
                    enable_clockin=False,
                )
                session.add(user)
                session.add(AppUser(phone="13900000001", password_hash=hash_password("old-password"), enabled=True))
                session.commit()
                session.refresh(user)
                user_id = user.id

            result = api.app_login(
                request=self.request,
                response=self.response,
                req=api.AppLoginRequest(phone="13900000001", password="correct-password-123"),
            )

        with Session(self.engine) as session:
            app_user = session.exec(select(AppUser).where(AppUser.phone == "13900000001")).one()

        self.assertEqual(result["user_id"], app_user.id)
        self.assertEqual(app_user.bound_user_id, user_id)
        self.assertTrue(app_user.enabled)
        self.assertTrue(verify_password("correct-password-123", app_user.password_hash))


if __name__ == "__main__":
    unittest.main()
