from typing import Any, Dict

from fastapi import HTTPException
from sqlmodel import Session

from server.models import DEFAULT_TENANT_ID
from server.secret_store import decrypt_secret, encrypt_secret
from server.settings_store import get_setting, upsert_setting

AI_SETTINGS_KEY = "ai"


def _settings_body(value: Any) -> Dict[str, Any]:
    data = dict(value) if isinstance(value, dict) else {}
    body = data.get("ai")
    return dict(body) if isinstance(body, dict) else data


def _decode_api_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return decrypt_secret(raw)
    except Exception:
        return ""


def normalize_ai_settings(value: Any) -> Dict[str, Any]:
    data = _settings_body(value)
    return {
        "apiUrl": str(data.get("apiUrl") or "").strip(),
        "apikey": _decode_api_key(data.get("apikey")),
        "model": str(data.get("model") or "").strip(),
    }


def sanitize_ai_settings_for_read(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "apiUrl": str(settings.get("apiUrl") or "").strip(),
        "apikey": "",
        "model": str(settings.get("model") or "").strip(),
        "hasApiKey": bool(str(settings.get("apikey") or "").strip()),
    }


def merge_ai_settings(payload: Any, current: Dict[str, Any] | None = None) -> Dict[str, Any]:
    incoming = _settings_body(payload)
    existing = current if isinstance(current, dict) else {}
    api_key = (
        str(incoming.get("apikey") or "").strip()
        if "apikey" in incoming
        else str(existing.get("apikey") or "").strip()
    )
    if "apikey" in incoming and not api_key:
        api_key = str(existing.get("apikey") or "").strip()
    return {
        "apiUrl": str(incoming.get("apiUrl") if "apiUrl" in incoming else existing.get("apiUrl", "")).strip(),
        "apikey": api_key,
        "model": str(incoming.get("model") if "model" in incoming else existing.get("model", "")).strip(),
    }


def validate_ai_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    normalized = merge_ai_settings(settings, {})
    if not normalized["apiUrl"]:
        raise HTTPException(status_code=400, detail="请填写 AI API URL")
    if not normalized["apikey"]:
        raise HTTPException(status_code=400, detail="请填写 AI API Key")
    if not normalized["model"]:
        raise HTTPException(status_code=400, detail="请填写 AI Model")
    return normalized


def load_global_ai_settings(session: Session, tenant_id: str = DEFAULT_TENANT_ID) -> Dict[str, Any]:
    row = get_setting(session, AI_SETTINGS_KEY, tenant_id)
    if not row and tenant_id != DEFAULT_TENANT_ID:
        row = get_setting(session, AI_SETTINGS_KEY, DEFAULT_TENANT_ID)
    return normalize_ai_settings(row.value if row and isinstance(row.value, dict) else {})


def save_global_ai_settings(session: Session, payload: Any, tenant_id: str = DEFAULT_TENANT_ID) -> Dict[str, Any]:
    current = load_global_ai_settings(session, tenant_id)
    settings = validate_ai_settings(merge_ai_settings(payload, current))
    stored = dict(settings)
    stored["apikey"] = encrypt_secret(str(stored.get("apikey") or ""))
    upsert_setting(session, AI_SETTINGS_KEY, {"ai": stored}, tenant_id)
    return settings
