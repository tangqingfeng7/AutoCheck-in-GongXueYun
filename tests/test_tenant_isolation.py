import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from server.models import AdminUser, AppUser, AuditLog, User, UserCreate


class TenantIsolationTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)

    def test_legacy_app_user_lookup_stays_within_tenant(self):
        from server.api import _get_authed_app_user

        with Session(self.engine) as session:
            default_app = AppUser(tenant_id="default", phone="13800000000", password_hash="hash", enabled=True, bound_user_id=1)
            acme_user = User(
                tenant_id="acme",
                phone="13800000000",
                password="encrypted",
                app_enabled=True,
                app_password_hash="hash",
            )
            session.add(default_app)
            session.add(acme_user)
            session.commit()
            session.refresh(acme_user)
            acme_user_id = acme_user.id

            result = _get_authed_app_user(session=session, payload={"sub": f"user:{acme_user_id}", "role": "user", "tenant_id": "acme"})

        self.assertEqual(result.tenant_id, "acme")
        self.assertEqual(result.bound_user_id, acme_user_id)

    def test_legacy_app_user_lookup_rejects_tenant_mismatch(self):
        from server.api import _get_authed_app_user

        with Session(self.engine) as session:
            acme_user = User(
                tenant_id="acme",
                phone="13800000001",
                password="encrypted",
                app_enabled=True,
                app_password_hash="hash",
            )
            session.add(acme_user)
            session.commit()
            session.refresh(acme_user)
            acme_user_id = acme_user.id

            with self.assertRaises(HTTPException) as ctx:
                _get_authed_app_user(
                    session=session,
                    payload={"sub": f"user:{acme_user_id}", "role": "user", "tenant_id": "default"},
                )

        self.assertEqual(ctx.exception.status_code, 401)

    def test_bound_task_user_rejects_cross_tenant_binding(self):
        from server.api import _get_bound_task_user

        with Session(self.engine) as session:
            default_user = User(tenant_id="default", phone="16600000000", password="encrypted")
            session.add(default_user)
            session.commit()
            session.refresh(default_user)
            app_user = AppUser(
                tenant_id="acme",
                phone="16600000000",
                password_hash="hash",
                enabled=True,
                bound_user_id=default_user.id,
            )

            with self.assertRaises(HTTPException) as ctx:
                _get_bound_task_user(session=session, app_user=app_user)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_app_bind_creates_or_reuses_user_in_same_tenant(self):
        from server import api

        with Session(self.engine) as session:
            acme_app = AppUser(tenant_id="acme", phone="15500000000", password_hash="hash", enabled=True)
            default_user = User(tenant_id="default", phone="15500000000", password="encrypted", app_enabled=True)
            session.add(acme_app)
            session.add(default_user)
            session.commit()
            session.refresh(acme_app)

        with patch.dict("os.environ", {"MOGUDING_BIND_VERIFY": "0"}, clear=False):
            with patch("server.api.engine", self.engine):
                with Session(self.engine) as session:
                    response = api.app_bind(
                        request=type("Req", (), {"headers": {}, "client": None})(),
                        session=session,
                        payload={"sub": f"app:{acme_app.id}", "role": "user", "tenant_id": "acme"},
                        req=api.AppBindRequest(task_phone="15500000000", task_password="new-password"),
                    )

        with Session(self.engine) as session:
            app_user = session.get(AppUser, acme_app.id)
            bound_user = session.get(User, response["user_id"])

        self.assertEqual(response["user_id"], bound_user.id)
        self.assertEqual(bound_user.tenant_id, "acme")
        self.assertEqual(app_user.bound_user_id, bound_user.id)
        self.assertEqual(bound_user.password, "new-password")

    def test_read_users_is_tenant_scoped_and_limited(self):
        from server.api import read_users

        with Session(self.engine) as session:
            for index in range(3):
                session.add(User(tenant_id="acme", phone=f"1390000000{index}", password="encrypted"))
            session.add(User(tenant_id="default", phone="13999999999", password="encrypted"))
            session.commit()

            users = read_users(
                session=session,
                admin={"sub": "admin", "role": "admin", "tenant_id": "acme"},
                limit=2,
                offset=1,
            )

        self.assertEqual([item["phone"] for item in users], ["13900000001", "13900000002"])

    def test_user_create_audit_log_uses_actor_tenant(self):
        from server.api import create_user

        with Session(self.engine) as session:
            create_user(
                session=session,
                operator={"sub": "operator", "role": "operator", "tenant_id": "acme"},
                user=UserCreate(phone="13700000000", password="encrypted", enable_clockin=False),
            )
            audit = session.exec(select(AuditLog).where(AuditLog.action == "user.create")).one()

        self.assertEqual(audit.tenant_id, "acme")

    def test_admin_disable_last_enabled_admin_is_tenant_scoped(self):
        from server import api

        with Session(self.engine) as session:
            default_admin = AdminUser(tenant_id="default", username="root", password_hash="hash", role="admin", enabled=True)
            acme_admin = AdminUser(tenant_id="acme", username="root", password_hash="hash", role="admin", enabled=True)
            session.add(default_admin)
            session.add(acme_admin)
            session.commit()
            session.refresh(acme_admin)

            with self.assertRaises(HTTPException) as ctx:
                api.update_admin_user(
                    session=session,
                    admin={"sub": "root", "role": "admin", "tenant_id": "acme"},
                    admin_user_id=acme_admin.id,
                    req=api.AdminUserUpdateRequest(enabled=False),
                )

            session.refresh(acme_admin)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertTrue(acme_admin.enabled)

    def test_tenant_management_api_surface_is_removed(self):
        from server import api

        for name in [
            "read_tenants_page",
            "create_tenant",
            "update_tenant",
            "TenantCreateRequest",
            "TenantUpdateRequest",
            "TenantPageResponse",
        ]:
            self.assertFalse(hasattr(api, name), name)

        paths = {getattr(route, "path", "") for route in api.router.routes}
        self.assertNotIn("/tenants/page", paths)
        self.assertNotIn("/tenants", paths)
        self.assertNotIn("/tenants/{tenant_id}", paths)


if __name__ == "__main__":
    unittest.main()
