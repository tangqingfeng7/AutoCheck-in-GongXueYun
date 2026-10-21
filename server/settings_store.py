from typing import Any

from sqlmodel import Session

from server.models import DEFAULT_TENANT_ID, SystemSetting


def normalize_setting_tenant_id(tenant_id: str | None) -> str:
    normalized = str(tenant_id or DEFAULT_TENANT_ID).strip()
    return normalized or DEFAULT_TENANT_ID


def setting_storage_key(key: str, tenant_id: str | None = DEFAULT_TENANT_ID) -> str:
    normalized_key = str(key or "").strip()
    if not normalized_key:
        raise ValueError("setting key is required")
    normalized_tenant = normalize_setting_tenant_id(tenant_id)
    if normalized_tenant == DEFAULT_TENANT_ID:
        return normalized_key
    return f"{normalized_tenant}:{normalized_key}"


def get_setting(session: Session, key: str, tenant_id: str | None = DEFAULT_TENANT_ID) -> SystemSetting | None:
    return session.get(SystemSetting, setting_storage_key(key, tenant_id))


def upsert_setting(
    session: Session,
    key: str,
    value: dict[str, Any],
    tenant_id: str | None = DEFAULT_TENANT_ID,
) -> SystemSetting:
    normalized_tenant = normalize_setting_tenant_id(tenant_id)
    storage_key = setting_storage_key(key, normalized_tenant)
    row = session.get(SystemSetting, storage_key)
    if not row:
        row = SystemSetting(key=storage_key, tenant_id=normalized_tenant, value={})
    row.tenant_id = normalized_tenant
    row.value = value if isinstance(value, dict) else {}
    session.add(row)
    return row
