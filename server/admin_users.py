import os
from sqlmodel import Session, select
from server.models import DEFAULT_TENANT_ID, AdminUser, AuditLog
from server.auth import hash_password
from server.security import require_safe_admin_credentials

def ensure_seed_admin_users() -> None:
    from server.database import engine
    app_env = (os.getenv("APP_ENV") or os.getenv("ENV") or "").strip().lower()

    admin_user = (os.getenv("ADMIN_USERNAME") or "admin").strip()
    admin_pass = (os.getenv("ADMIN_PASSWORD") or "admin123456").strip()
    require_safe_admin_credentials(admin_user, admin_pass)

    with Session(engine) as session:
        has_any = session.exec(select(AdminUser).limit(1)).first() is not None
        if app_env in ["prod", "production"]:
            if os.getenv("ADMIN_USERNAME") is None or os.getenv("ADMIN_PASSWORD") is None:
                raise RuntimeError("生产环境必须设置 ADMIN_USERNAME / ADMIN_PASSWORD")

        if admin_user and admin_pass and not (app_env in ["prod", "production"] and has_any):
            existing = session.exec(
                select(AdminUser).where((AdminUser.tenant_id == DEFAULT_TENANT_ID) & (AdminUser.username == admin_user))
            ).first()
            if existing:
                if existing.role != "admin":
                    existing.role = "admin"
                if existing.enabled is not True:
                    existing.enabled = True
                session.add(existing)
            else:
                session.add(
                    AdminUser(
                        username=admin_user,
                        password_hash=hash_password(admin_pass),
                        role="admin",
                        enabled=True,
                    )
                )
            session.add(AuditLog(actor="system", action="admin_user.seed", target_user_id=None, detail={"username": admin_user, "role": "admin"}))

        session.commit()
