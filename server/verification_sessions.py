import datetime as dt
import json
import re
import time
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlmodel import Session, select

from server.database import engine
from server.models import SystemSetting, User
from server.secret_store import encrypt_secret, decrypt_secret
from server.settings_store import get_setting, upsert_setting
from server.attendance_confirmation import confirm_attendance
from server.attendance_reconciliation import reconcile_user
from server.execution_locks import acquire_task_lock, release_task_lock

PREFIX = "verification-session:"
TERMINAL = {"record_confirmed", "superseded", "expired"}
PUBLIC_FIELDS = {"id", "user_id", "attendance_date", "target_type", "verification_type", "state",
                 "created_at", "expires_at", "updated_at", "last_checked", "verification_confirmed",
                 "record_confirmed", "server_time", "check_state"}


def public(value):
    result = {k: v for k, v in value.items() if k in PUBLIC_FIELDS}
    if time.time() >= value.get("expires_at", 0) and value.get("state") not in TERMINAL:
        result["state"] = "expired"
    return result


def create_session(user_id, tenant_id, day, kind, details, *, db_engine=None):
    db = db_engine if db_engine is not None else engine
    dt.date.fromisoformat(day)
    parsed = urlsplit(str(details.get("registerUrl") or ""))
    verification_type = details.get("verification_type")
    if kind not in {"START", "END", "HOLIDAY"} or verification_type not in {"account", "face"}:
        raise ValueError("授权事务类型无效")
    if parsed.scheme.lower() != "alipays" or not parsed.netloc:
        raise ValueError("授权事务链接无效")
    registration = str(details.get("outRegisterNo") or "")
    if verification_type == "account" and not re.fullmatch(r"[A-Za-z0-9-]{1,128}", registration):
        raise ValueError("授权事务登记编号无效")
    payload = encrypt_secret(json.dumps({"registerUrl": details["registerUrl"], "outRegisterNo": registration}))
    if not payload.startswith("enc$"):
        raise ValueError("授权事务需要配置加密密钥")
    sid = uuid.uuid4().hex
    now = time.time()
    value = {"id": sid, "user_id": int(user_id), "attendance_date": day, "target_type": kind,
             "verification_type": verification_type, "state": "awaiting_verification", "payload": payload,
             "created_at": now, "updated_at": now, "expires_at": now + 1800,
             "verification_confirmed": False, "record_confirmed": False}
    with Session(db) as s:
        upsert_setting(s, PREFIX + sid, value, tenant_id); s.commit()
    return sid


def _owned(s, user, sid):
    if not re.fullmatch(r"[0-9a-f]{32}", sid):
        raise HTTPException(status_code=404, detail="授权事务不存在")
    row = get_setting(s, PREFIX + sid, user.tenant_id)
    if not row or row.tenant_id != user.tenant_id or (row.value or {}).get("user_id") != user.id:
        raise HTTPException(status_code=404, detail="授权事务不存在")
    return row


def list_sessions(s, user):
    rows = s.exec(select(SystemSetting).where(SystemSetting.tenant_id == user.tenant_id)
                  .where(SystemSetting.key.contains(PREFIX))).all()
    values = [row.value for row in rows if (row.value or {}).get("user_id") == user.id]
    return [public(v) for v in sorted(values, key=lambda v: v.get("created_at", 0), reverse=True)[:20]]


def session_links(user, sid, *, db_engine=None):
    from server.util.MessagePush import MessagePusher
    import base64
    db = db_engine if db_engine is not None else engine
    with Session(db) as s:
        value = dict(_owned(s, user, sid).value)
        if public(value)["state"] in TERMINAL:
            raise HTTPException(status_code=410, detail="授权事务已结束或过期，请先检查服务端记录，勿重复签到")
        try:
            payload = json.loads(decrypt_secret(value["payload"]))
        except Exception:
            raise HTTPException(status_code=409, detail="授权上下文无法解密，请检查服务端密钥")
    url = MessagePusher._safe_alipay_url(payload.get("registerUrl"))
    if not url:
        raise HTTPException(status_code=409, detail="授权链接无效")
    return {**public(value), "direct_url": url, "browser_url": MessagePusher._alipay_browser_url(url),
            "qr_data_url": "data:image/png;base64," + base64.b64encode(MessagePusher._qr_png(url)).decode()}


def mark_confirmed(s, user, day, checks):
    confirmed = {c["target_type"]: c for c in checks if c.get("record_confirmed")}
    for meta in list_sessions(s, user):
        match = confirmed.get(meta.get("target_type"))
        if meta.get("attendance_date") != day or not match:
            continue
        row = _owned(s, user, meta["id"])
        value = {**row.value, "state": "record_confirmed", "record_confirmed": True,
                 "payload": "", "updated_at": time.time(), "server_time": match.get("server_time")}
        upsert_setting(s, PREFIX + meta["id"], value, user.tenant_id)
        from server.mail_delivery import cancel_pending
        cancel_pending(s, user.tenant_id, verification_session_id=meta["id"])


def mark_verified(s, user, day, kind, registration):
    """Compatibility for the existing immediate-dialog check, scoped to its own transaction."""
    for meta in list_sessions(s, user):
        if (meta.get("attendance_date") != day or meta.get("target_type") != kind
                or meta.get("verification_type") != "account" or meta.get("state") in TERMINAL):
            continue
        row = _owned(s, user, meta["id"])
        try:
            payload = json.loads(decrypt_secret(row.value["payload"]))
        except Exception:
            continue
        if payload.get("outRegisterNo") == registration:
            value = {**row.value, "verification_confirmed": True, "state": "verified_pending_record",
                     "updated_at": time.time(), "last_checked": time.time()}
            upsert_setting(s, PREFIX + meta["id"], value, user.tenant_id)


def check_session(user, sid, *, db_engine=None):
    db = db_engine if db_engine is not None else engine
    with Session(db) as s:
        _owned(s, user, sid)  # validate scope and identifier length before creating any lock
    token = acquire_task_lock(f"verification-check:{user.tenant_id}:{sid}", ttl_seconds=120, db_engine=db)
    if token is None:
        raise HTTPException(status_code=409, detail="本次授权正在检查，请稍后刷新")
    try:
        with Session(db) as s:
            value = dict(_owned(s, user, sid).value)
        if value["state"] == "record_confirmed" or time.time() - value.get("last_checked", 0) < 15:
            return public(value)
        from server.coreApi.MainLogicApi import ApiClient
        from server.user_runtime import user_to_config, runtime_login_valid
        from server.util.Config import ConfigManager
        config = user_to_config(user)
        if not runtime_login_valid(config.get("userInfo")):
            raise HTTPException(status_code=409, detail="工学云登录已过期，请先刷新登录状态")
        client = ApiClient(ConfigManager(config=config))
        value["last_checked"] = time.time()
        value["check_state"] = "checked"
        expired = time.time() >= value["expires_at"]
        if value["verification_type"] == "account" and not expired and not value["verification_confirmed"]:
            try:
                payload = json.loads(decrypt_secret(value["payload"]))
                response = client.query_alipay_clockin_verification(payload["outRegisterNo"])
                # A user click or an HTTP 200 alone is NOT proof of completed verification.
                value["verification_confirmed"] = response.get("code") == 200 and response.get("data") is True
            except Exception:
                value["check_state"] = "verification_query_failed"
        check = confirm_attendance(client, value["attendance_date"], value["target_type"], attempts=3, delay=0.5)
        if check["record_confirmed"]:
            value.update(state="record_confirmed", record_confirmed=True, payload="", server_time=check["server_time"])
        elif expired:
            value.update(state="expired", payload="")
        else:
            value["state"] = "verified_pending_record" if value["verification_confirmed"] else "awaiting_verification"
        if check["confirmation_state"] == "query_failed":
            value["check_state"] = "record_query_failed"
        value["updated_at"] = time.time()
        with Session(db) as s:
            live_user = s.get(User, user.id)
            if not live_user or live_user.tenant_id != user.tenant_id or live_user.deleted_at is not None:
                raise HTTPException(status_code=404, detail="账号不存在")
            # Reload after the remote read: a background detector may already have confirmed it.
            current = dict(_owned(s, user, sid).value)
            if current.get("state") == "record_confirmed":
                return public(current)
            upsert_setting(s, PREFIX + sid, value, user.tenant_id)
            if value["state"] in TERMINAL:
                from server.mail_delivery import cancel_pending
                cancel_pending(s, user.tenant_id, verification_session_id=sid)
            reconcile_user(s, live_user, value["attendance_date"],
                           [{**check, "verification_confirmed": value["verification_confirmed"]}])
            s.commit()
        return public(value)
    finally:
        release_task_lock(token, db_engine=db)


def cleanup_sessions():
    from server.mail_delivery import cancel_pending
    with Session(engine) as s:
        rows = s.exec(select(SystemSetting).where(SystemSetting.key.contains(PREFIX))).all()
        for row in rows:
            value = dict(row.value or {})
            if time.time() - value.get("created_at", time.time()) > 7 * 86400:
                s.delete(row)
            elif time.time() >= value.get("expires_at", 0) and value.get("state") not in TERMINAL:
                row.value = {**value, "state": "expired", "payload": "", "updated_at": time.time()}
                s.add(row)
                cancel_pending(s, row.tenant_id, verification_session_id=value.get("id"))
        s.commit()
