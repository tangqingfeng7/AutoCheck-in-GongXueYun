"""Tenant-scoped PushPlus credentials. Never expose provider response bodies."""
from sqlmodel import Session

from server.models import DEFAULT_TENANT_ID
from server.secret_store import decrypt_secret, encrypt_secret
from server.settings_store import get_setting, upsert_setting


def normalize_pushplus(value):
    data = value if isinstance(value, dict) else {}
    return {"type": "PushPlus", "enabled": bool(data.get("enabled", False)),
            "token": str(data.get("token") or "").strip(),
            "secretKey": str(data.get("secretKey") or "").strip(),
            "uploadQr": bool(data.get("uploadQr", False)),
            "clawbotEnabled": bool(data.get("clawbotEnabled", False)),
            "fallbackEnabled": bool(data.get("fallbackEnabled", False))}


def load_pushplus(session, tenant_id=DEFAULT_TENANT_ID):
    row = get_setting(session, "pushplus", tenant_id)
    data = normalize_pushplus(row.value if row else {})
    for field in ("token", "secretKey"):
        try:
            data[field] = decrypt_secret(data[field])
        except ValueError:
            data[field] = ""
    return data


def sanitize_pushplus(data):
    clean = normalize_pushplus(data)
    for field, flag in (("token", "hasToken"), ("secretKey", "hasSecretKey")):
        clean[flag] = bool(clean.pop(field))
    return clean


def resolve_pushplus(incoming, current):
    data = dict(current)
    for field in ("enabled", "uploadQr", "clawbotEnabled", "fallbackEnabled", "token", "secretKey"):
        if field in incoming and (field not in {"token", "secretKey"} or str(incoming[field] or "").strip()):
            data[field] = incoming[field]
    data = normalize_pushplus(data)
    if data["enabled"] and not data["token"]:
        raise ValueError("启用 PushPlus 请填写 Token")
    if data["uploadQr"] and not data["secretKey"]:
        raise ValueError("上传授权二维码需要 PushPlus SecretKey 和图片服务权限")
    if any(len(data[field]) > 256 for field in ("token", "secretKey")):
        raise ValueError("PushPlus 凭据长度无效")
    return data


def save_pushplus(session, incoming, tenant_id=DEFAULT_TENANT_ID):
    data = resolve_pushplus(incoming, load_pushplus(session, tenant_id))
    stored = dict(data)
    for field in ("token", "secretKey"):
        stored[field] = encrypt_secret(data[field])
        if data[field] and not stored[field].startswith("enc$"):
            raise ValueError("请先配置 USER_PASSWORD_KEY，PushPlus 凭据必须加密保存")
    upsert_setting(session, "pushplus", stored, tenant_id)
    return sanitize_pushplus(data)


def load_global_pushplus(tenant_id=DEFAULT_TENANT_ID, *, db_engine=None):
    from server.database import engine
    with Session(db_engine if db_engine is not None else engine) as session:
        return load_pushplus(session, tenant_id)
