import unittest
from unittest.mock import patch

from fastapi import Depends, FastAPI, Response
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from server.auth import get_admin, get_user, issue_token, set_auth_cookie, validate_token_subject, verify_token
from server.api import _login_payload
from server.models import AdminUser, AppUser


def _set_cookie_header(response: Response) -> str:
    return "\n".join(
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ).lower()


class AuthCookieFlowTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            "os.environ",
            {
                "APP_SECRET": "test-secret-value-with-more-than-thirty-two-chars",
                "RETURN_AUTH_TOKEN": "",
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        import server.auth as auth

        auth._SECRET_CACHE = None

    def test_cookie_auth_works_for_fastapi_dependency_without_bearer_header(self):
        app = FastAPI()

        @app.get("/api/app/probe")
        def app_probe(payload: dict = Depends(get_user)):
            return {"sub": payload["sub"], "role": payload["role"]}

        token = issue_token("app:1", "user")
        client = TestClient(app)
        client.cookies.set("app_auth_token", token)

        resp = client.get("/api/app/probe")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["sub"], "app:1")

    def test_admin_cookie_is_preferred_on_admin_routes_when_both_cookies_exist(self):
        app = FastAPI()

        @app.get("/api/admin/probe")
        def admin_probe(payload: dict = Depends(get_admin)):
            return {"sub": payload["sub"], "role": payload["role"]}

        client = TestClient(app)
        client.cookies.set("app_auth_token", issue_token("app:1", "user"))
        client.cookies.set("admin_auth_token", issue_token("admin", "admin"))

        resp = client.get("/api/admin/probe")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["role"], "admin")

    def test_login_payload_does_not_return_token_by_default(self):
        self.assertNotIn("token", _login_payload("secret-token", {"role": "admin"}))

    def test_set_auth_cookie_marks_cookie_httponly(self):
        response = Response()
        set_auth_cookie(response, "secret-token", "admin")

        header = response.headers["set-cookie"].lower()
        self.assertIn("httponly", header)
        self.assertNotIn("secret-token", _login_payload("secret-token", {"role": "admin"}).values())

    def test_auth_cookie_is_secure_by_default_in_production_and_sets_csrf_cookie(self):
        response = Response()

        with patch.dict("os.environ", {"APP_ENV": "production", "AUTH_COOKIE_SECURE": ""}, clear=False):
            set_auth_cookie(response, "secret-token", "admin")

        header = _set_cookie_header(response)
        self.assertIn("admin_auth_token=", header)
        self.assertIn("csrf_token=", header)
        self.assertIn("secure", header)
        self.assertIn("httponly", header)

    def test_auth_cookie_secure_flag_can_be_disabled_for_plain_http_development(self):
        response = Response()

        with patch.dict("os.environ", {"APP_ENV": "production", "AUTH_COOKIE_SECURE": "false"}, clear=False):
            set_auth_cookie(response, "secret-token", "admin")

        self.assertNotIn("secure", response.headers["set-cookie"].lower())

    def test_role_permissions_are_explicit(self):
        from server.auth import has_permission, permissions_for_role

        self.assertTrue(has_permission({"role": "admin"}, "audit:purge"))
        self.assertTrue(has_permission({"role": "admin"}, "settings:read"))
        self.assertFalse(has_permission({"role": "admin", "tenant_id": "default"}, "tenants:manage"))
        self.assertFalse(has_permission({"role": "admin", "tenant_id": "acme"}, "tenants:manage"))
        self.assertFalse(has_permission({"role": "operator"}, "audit:purge"))
        self.assertIn("users:read", permissions_for_role("viewer"))

    def test_role_permissions_can_be_overridden_from_env(self):
        from server.auth import has_permission, permissions_for_role

        with patch.dict(
            "os.environ",
            {"ROLE_PERMISSIONS_JSON": '{"viewer":["users:read"],"operator":["users:read","tasks:run"]}'},
            clear=False,
        ):
            self.assertEqual(permissions_for_role("viewer"), {"users:read"})
            self.assertTrue(has_permission({"role": "operator"}, "tasks:run"))
            self.assertFalse(has_permission({"role": "operator"}, "batch:manage"))

    def test_admin_me_returns_identity_and_permissions_without_tenant(self):
        from server.api import admin_me

        payload = {"sub": "alice", "role": "operator", "tenant_id": "acme"}

        data = admin_me(payload=payload)

        self.assertEqual(data["username"], "alice")
        self.assertNotIn("tenant_id", data)
        self.assertEqual(data["role"], "operator")
        self.assertIn("users:read", data["permissions"])
        self.assertNotIn("tenants:manage", data["permissions"])

    def test_admin_me_does_not_expose_tenant_management(self):
        from server.api import admin_me

        payload = {"sub": "alice", "role": "admin", "tenant_id": "acme"}

        data = admin_me(payload=payload)

        self.assertNotIn("tenant_id", data)
        self.assertIn("users:read", data["permissions"])
        self.assertNotIn("tenants:read", data["permissions"])
        self.assertNotIn("tenants:manage", data["permissions"])

    def test_admin_logout_revokes_current_token_version(self):
        from server.api import admin_logout

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(AdminUser(tenant_id="default", username="admin", password_hash="hash", role="admin", token_version=0))
            session.commit()

            token = issue_token("admin", "admin", tenant_id="default", token_version=0)
            payload = verify_token(token)
            response = Response()

            result = admin_logout(response=response, session=session, payload=payload)

            self.assertEqual(result["ok"], True)

        with self.assertRaises(Exception):
            validate_token_subject(payload, db_engine=engine)

    def test_app_logout_revokes_current_token_version(self):
        from server.api import app_logout

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(AppUser(id=7, tenant_id="acme", phone="13800000000", password_hash="hash", token_version=0))
            session.commit()

            token = issue_token("app:7", "user", tenant_id="acme", token_version=0)
            payload = verify_token(token)
            response = Response()

            result = app_logout(response=response, session=session, payload=payload)

            self.assertEqual(result["ok"], True)

        with self.assertRaises(Exception):
            validate_token_subject(payload, db_engine=engine)

    def test_logout_without_valid_payload_still_clears_cookie(self):
        from server.api import admin_logout, app_logout

        admin_response = Response()
        app_response = Response()

        self.assertEqual(admin_logout(response=admin_response, session=None, payload=None)["ok"], True)
        self.assertEqual(app_logout(response=app_response, session=None, payload=None)["ok"], True)
        self.assertIn("admin_auth_token", admin_response.headers["set-cookie"])
        self.assertIn("app_auth_token", app_response.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()
