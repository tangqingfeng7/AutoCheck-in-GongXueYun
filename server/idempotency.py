from __future__ import annotations

import hashlib
import json
import datetime
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from server.models import SystemSetting
from server.settings_store import normalize_setting_tenant_id, setting_storage_key, upsert_setting
from server.time_utils import utc_now

IDEMPOTENCY_STATUS_PENDING = "pending"
IDEMPOTENCY_STATUS_COMPLETED = "completed"
IDEMPOTENCY_STATUS_FAILED = "failed"
DEFAULT_IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600


def build_idempotency_request_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_expired(value: dict[str, Any], ttl_seconds: Optional[int]) -> bool:
    raw_updated_at = str(value.get("updated_at") or "").strip()
    if not raw_updated_at:
        return False
    try:
        updated_at = datetime.datetime.fromisoformat(raw_updated_at.replace("Z", "+00:00"))
    except Exception:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=utc_now().tzinfo)
    ttl = DEFAULT_IDEMPOTENCY_TTL_SECONDS if ttl_seconds is None else max(300, int(ttl_seconds))
    return (utc_now() - updated_at).total_seconds() > ttl


def _idempotency_value(
    *,
    request_hash: str,
    status: str,
    response: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "fingerprint": request_hash,
        "status": status,
        "updated_at": utc_now().isoformat(timespec="seconds"),
    }
    if response is not None:
        value["response"] = response
    if error:
        value["error"] = str(error)[:500]
    return value


def _storage_key(logical_key: str, tenant_id: str | None) -> tuple[str, str]:
    normalized_tenant = normalize_setting_tenant_id(tenant_id)
    return setting_storage_key(logical_key, normalized_tenant), normalized_tenant


def _peek_record(
    *,
    db_engine,
    logical_key: str,
    tenant_id: str | None,
    request_hash: str,
    conflict_detail: str,
    pending_detail: str,
    ttl_seconds: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    storage_key, normalized_tenant = _storage_key(logical_key, tenant_id)
    with Session(db_engine) as session:
        record = session.get(SystemSetting, storage_key)
        if not record:
            return None
        if not isinstance(record.value, dict):
            session.delete(record)
            session.commit()
            return None

        value = record.value
        if _record_expired(value, ttl_seconds):
            session.delete(record)
            session.commit()
            return None

        if str(value.get("fingerprint") or "") != request_hash:
            raise HTTPException(status_code=409, detail=conflict_detail)

        status = str(value.get("status") or "").lower()
        if status == IDEMPOTENCY_STATUS_COMPLETED and isinstance(value.get("response"), dict):
            return dict(value["response"])
        if status == IDEMPOTENCY_STATUS_PENDING:
            raise HTTPException(status_code=409, detail=pending_detail)
        if status == IDEMPOTENCY_STATUS_FAILED:
            session.delete(record)
            session.commit()
            return None
        return None


def claim_idempotency_record(
    *,
    db_engine,
    tenant_id: str | None,
    logical_key: str,
    request_hash: str,
    conflict_detail: str = "Idempotency key already used with different request parameters",
    pending_detail: str = "Request is already being processed",
    ttl_seconds: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    storage_key, normalized_tenant = _storage_key(logical_key, tenant_id)
    while True:
        with Session(db_engine) as session:
            record = session.get(SystemSetting, storage_key)
            if record:
                if not isinstance(record.value, dict):
                    session.delete(record)
                    session.commit()
                    continue
                value = record.value
                if _record_expired(value, ttl_seconds):
                    session.delete(record)
                    session.commit()
                    continue
                if str(value.get("fingerprint") or "") != request_hash:
                    raise HTTPException(status_code=409, detail=conflict_detail)
                status = str(value.get("status") or "").lower()
                if status == IDEMPOTENCY_STATUS_COMPLETED and isinstance(value.get("response"), dict):
                    return dict(value["response"])
                if status == IDEMPOTENCY_STATUS_PENDING:
                    raise HTTPException(status_code=409, detail=pending_detail)
                if status == IDEMPOTENCY_STATUS_FAILED:
                    session.delete(record)
                    session.commit()
                    continue
                session.delete(record)
                session.commit()
                continue

            pending_value = _idempotency_value(request_hash=request_hash, status=IDEMPOTENCY_STATUS_PENDING)
            session.add(SystemSetting(key=storage_key, tenant_id=normalized_tenant, value=pending_value))
            try:
                session.commit()
                return None
            except IntegrityError:
                session.rollback()
                continue


def finalize_idempotency_record(
    *,
    db_engine,
    tenant_id: str | None,
    logical_key: str,
    request_hash: str,
    status: str = IDEMPOTENCY_STATUS_COMPLETED,
    response: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    storage_key, normalized_tenant = _storage_key(logical_key, tenant_id)
    with Session(db_engine) as session:
        record = session.get(SystemSetting, storage_key)
        if record and isinstance(record.value, dict):
            value = record.value
            if str(value.get("fingerprint") or "") != request_hash:
                raise HTTPException(status_code=409, detail="Idempotency key already used with different request parameters")

        upsert_setting(
            session,
            logical_key,
            _idempotency_value(
                request_hash=request_hash,
                status=status,
                response=response,
                error=error,
            ),
            normalized_tenant,
        )
        session.commit()


def peek_idempotency_response(
    *,
    db_engine,
    tenant_id: str | None,
    logical_key: str,
    request_hash: str,
    conflict_detail: str = "Idempotency key already used with different request parameters",
    pending_detail: str = "Request is already being processed",
    ttl_seconds: Optional[int] = None,
) -> Optional[dict[str, Any]]:
    return _peek_record(
        db_engine=db_engine,
        logical_key=logical_key,
        tenant_id=tenant_id,
        request_hash=request_hash,
        conflict_detail=conflict_detail,
        pending_detail=pending_detail,
        ttl_seconds=ttl_seconds,
    )
