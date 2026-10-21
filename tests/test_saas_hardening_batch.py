import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine


class SaasHardeningBatchTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        import server.models  # noqa: F401 - 在 create_all 前加载 SQLModel 元数据

        SQLModel.metadata.create_all(self.engine)

    def test_user_phone_uniqueness_is_scoped_to_tenant(self):
        from server.models import User

        with Session(self.engine) as session:
            session.add(User(tenant_id="default", phone="13800000000", password="encrypted"))
            session.add(User(tenant_id="acme", phone="13800000000", password="encrypted"))
            session.commit()

            session.add(User(tenant_id="acme", phone="13800000000", password="encrypted"))
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_admin_and_app_login_names_are_scoped_to_tenant(self):
        from server.models import AdminUser, AppUser

        with Session(self.engine) as session:
            session.add(AdminUser(tenant_id="default", username="admin", password_hash="hash"))
            session.add(AdminUser(tenant_id="acme", username="admin", password_hash="hash"))
            session.add(AppUser(tenant_id="default", phone="13800000000", password_hash="hash"))
            session.add(AppUser(tenant_id="acme", phone="13800000000", password_hash="hash"))
            session.commit()

    def test_token_version_rejects_stale_admin_token(self):
        from server.auth import validate_token_subject
        from server.models import AdminUser

        with Session(self.engine) as session:
            session.add(AdminUser(username="admin", password_hash="hash", token_version=1))
            session.commit()

        payload = {"sub": "admin", "role": "admin", "tenant_id": "default", "ver": 0}
        with self.assertRaises(HTTPException) as ctx:
            validate_token_subject(payload, db_engine=self.engine)

        self.assertEqual(ctx.exception.status_code, 401)

    def test_token_version_accepts_current_app_token(self):
        from server.auth import validate_token_subject
        from server.models import AppUser

        with Session(self.engine) as session:
            session.add(AppUser(id=7, phone="13800000000", password_hash="hash", token_version=2))
            session.commit()

        payload = {"sub": "app:7", "role": "user", "tenant_id": "default", "ver": 2}

        self.assertEqual(validate_token_subject(payload, db_engine=self.engine), payload)

    def test_token_version_rejects_malformed_user_subject(self):
        from server.auth import validate_token_subject

        payload = {"sub": "7", "role": "user", "tenant_id": "default", "ver": 0}

        with self.assertRaises(HTTPException):
            validate_token_subject(payload, db_engine=self.engine)

    def test_disabled_tenant_rejects_current_tokens(self):
        from server.auth import validate_token_subject
        from server.models import AdminUser, Tenant

        with Session(self.engine) as session:
            session.add(Tenant(id="acme", name="Acme", status="disabled"))
            session.add(AdminUser(tenant_id="acme", username="admin", password_hash="hash", role="admin", token_version=0))
            session.commit()

        payload = {"sub": "admin", "role": "admin", "tenant_id": "acme", "ver": 0}

        with self.assertRaises(HTTPException) as ctx:
            validate_token_subject(payload, db_engine=self.engine)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_production_rejects_legacy_tokens_without_version(self):
        from server.auth import validate_token_subject

        payload = {"sub": "admin", "role": "admin", "tenant_id": "default"}
        with patch.dict("os.environ", {"APP_ENV": "production", "ALLOW_LEGACY_TOKENS": ""}, clear=True):
            with self.assertRaises(HTTPException) as ctx:
                validate_token_subject(payload)

        self.assertEqual(ctx.exception.status_code, 401)

    def test_legacy_tokens_require_explicit_compatibility_switch(self):
        from server.auth import validate_token_subject

        payload = {"sub": "admin", "role": "admin", "tenant_id": "default"}
        with patch.dict("os.environ", {"APP_ENV": "production", "ALLOW_LEGACY_TOKENS": "true"}, clear=True):
            self.assertEqual(validate_token_subject(payload), payload)

    def test_captcha_model_auto_download_is_disabled_by_default_in_production(self):
        from server.main import _should_auto_download_captcha_models

        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            self.assertFalse(_should_auto_download_captcha_models())
        with patch.dict("os.environ", {"APP_ENV": "production", "CAPTCHA_MODEL_AUTO_DOWNLOAD": "true"}, clear=True):
            self.assertTrue(_should_auto_download_captcha_models())

    def test_production_captcha_model_download_requires_checksum(self):
        from server.util.CaptchaUtils import ensure_model_exists

        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "CAPTCHA_MODEL_REQUIRE_CHECKSUM": "true", "MODEL_DIR": "unused"},
            clear=True,
        ):
            with patch("server.util.CaptchaUtils.get_model_path", return_value="missing.onnx"):
                with patch("server.util.CaptchaUtils.os.path.exists", return_value=False):
                    with self.assertRaises(ValueError):
                        ensure_model_exists("ocr.onnx", "https://example.com/ocr.onnx")

    def test_captcha_model_download_rejects_checksum_mismatch(self):
        from server.util.CaptchaUtils import ensure_model_exists

        response = Mock()
        response.raise_for_status.return_value = None
        response.iter_content.return_value = [b"bad-model"]

        with patch.dict(
            "os.environ",
            {
                "CAPTCHA_MODEL_REQUIRE_CHECKSUM": "true",
                "CAPTCHA_MODEL_SHA256_OCR_ONNX": "0" * 64,
            },
            clear=True,
        ):
            with patch("server.util.CaptchaUtils.get_model_path", return_value="missing.onnx"):
                with patch("server.util.CaptchaUtils.os.path.exists", side_effect=[False, True]):
                    with patch("server.util.CaptchaUtils.os.makedirs"):
                        with patch("server.util.CaptchaUtils.requests.get", return_value=response):
                            with patch("builtins.open", unittest.mock.mock_open()):
                                with patch("server.util.CaptchaUtils.os.remove") as remove:
                                    with self.assertRaises(ValueError):
                                        ensure_model_exists("ocr.onnx", "https://example.com/ocr.onnx")

        remove.assert_called()


if __name__ == "__main__":
    unittest.main()
