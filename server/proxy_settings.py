from typing import Any, Dict

from sqlmodel import Session

from server.database import engine
from server.models import DEFAULT_TENANT_ID
from server.secret_store import decrypt_secret, encrypt_secret
from server.settings_store import get_setting

PROXY_SETTINGS_KEY = "moguding_proxy"
DEFAULT_PROXY_TTL_SECONDS = 55.0
DEFAULT_PROXY_API_TIMEOUT_SECONDS = 10.0
MAX_PROXY_TTL_SECONDS = 600.0
MAX_PROXY_API_TIMEOUT_SECONDS = 30.0


def _float_value(value: Any, default: float, max_value: float) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return 0.0
    return min(parsed, max_value)


def normalize_proxy_settings(settings: Any, existing: Any = None) -> Dict[str, Any]:
    incoming = settings if isinstance(settings, dict) else {}
    current = existing if isinstance(existing, dict) else {}
    return {
        "enabled": bool(incoming["enabled"] if "enabled" in incoming else current.get("enabled", False)),
        "apiUrl": str(incoming.get("apiUrl") if "apiUrl" in incoming else current.get("apiUrl", "")).strip(),
        "ttlSeconds": _float_value(
            incoming.get("ttlSeconds") if "ttlSeconds" in incoming else current.get("ttlSeconds", DEFAULT_PROXY_TTL_SECONDS),
            DEFAULT_PROXY_TTL_SECONDS,
            MAX_PROXY_TTL_SECONDS,
        ),
        "apiTimeoutSeconds": _float_value(
            incoming.get("apiTimeoutSeconds")
            if "apiTimeoutSeconds" in incoming
            else current.get("apiTimeoutSeconds", DEFAULT_PROXY_API_TIMEOUT_SECONDS),
            DEFAULT_PROXY_API_TIMEOUT_SECONDS,
            MAX_PROXY_API_TIMEOUT_SECONDS,
        ),
        "proxyUrls": str(incoming.get("proxyUrls") if "proxyUrls" in incoming else current.get("proxyUrls", "")).strip(),
    }


def _decode_proxy_settings(raw: Any) -> Dict[str, Any]:
    data = dict(raw) if isinstance(raw, dict) else {}
    if "apiUrl" in data:
        try:
            data["apiUrl"] = decrypt_secret(str(data.get("apiUrl") or ""))
        except Exception:
            data["apiUrl"] = ""
    return data


def encode_proxy_settings(settings: Any) -> Dict[str, Any]:
    normalized = normalize_proxy_settings(settings)
    stored = dict(normalized)
    if stored.get("apiUrl"):
        stored["apiUrl"] = encrypt_secret(str(stored.get("apiUrl") or ""))
    return stored


def load_global_proxy_settings(tenant_id: str = DEFAULT_TENANT_ID) -> Dict[str, Any]:
    try:
        with Session(engine) as session:
            row = get_setting(session, PROXY_SETTINGS_KEY, tenant_id)
            if not row and tenant_id != DEFAULT_TENANT_ID:
                row = get_setting(session, PROXY_SETTINGS_KEY, DEFAULT_TENANT_ID)
            raw = row.value if row and isinstance(row.value, dict) else {}
        return normalize_proxy_settings(_decode_proxy_settings(raw))
    except Exception:
        return normalize_proxy_settings({})
