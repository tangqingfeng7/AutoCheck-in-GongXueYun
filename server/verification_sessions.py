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
from server.settings_store import get_setting, upsert_setting, setting_storage_key
from server.attendance_confirmation import confirm_attendance, verification_query_succeeded, continuation_context_supported
from server.attendance_reconciliation import reconcile_user
from server.execution_locks import acquire_task_lock, release_task_lock

PREFIX = "verification-session:"
VERIFICATION_POLL_SECONDS = 3
TERMINAL = {"record_confirmed", "superseded", "expired"}
PUBLIC_FIELDS = {"id", "user_id", "attendance_date", "target_type", "verification_type", "state",
                 "created_at", "expires_at", "updated_at", "last_checked", "verification_confirmed",
                 "record_confirmed", "server_time", "check_state", "has_submission_context",
                 "resume_state", "resume_attempted", "resume_attempted_at"}


def public(value):
    result = {k: v for k, v in value.items() if k in PUBLIC_FIELDS}
    if time.time() >= value.get("expires_at", 0) and value.get("state") not in TERMINAL:
        result["state"] = "expired"
    result["resume_available"] = bool(value.get("has_submission_context")
                                      and not value.get("resume_attempted")
                                      and result.get("state") not in TERMINAL
                                      and value.get("verification_type") == "account")
    if result.get("state") not in TERMINAL and not value.get("resume_attempted"):
        result["resume_state"] = value.get("resume_state") or "context_missing"
    return result


def create_session(user_id, tenant_id, day, kind, details, *, db_engine=None, submission_context=None):
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
    private = {"registerUrl": details["registerUrl"], "outRegisterNo": registration}
    has_context = isinstance(submission_context, dict) and isinstance(submission_context.get("body"), dict)
    resumable = has_context and continuation_context_supported(submission_context)
    if has_context:
        # Never put the original request or official opaque response in public
        # execution results, notifications or logs.
        private["submission_context"] = submission_context
    payload = encrypt_secret(json.dumps(private))
    if not payload.startswith("enc$"):
        raise ValueError("授权事务需要配置加密密钥")
    sid = uuid.uuid4().hex
    now = time.time()
    value = {"id": sid, "user_id": int(user_id), "attendance_date": day, "target_type": kind,
             "verification_type": verification_type, "state": "awaiting_verification", "payload": payload,
             "created_at": now, "updated_at": now, "expires_at": now + 1800,
             "verification_confirmed": False, "record_confirmed": False,
             "has_submission_context": bool(resumable), "resume_attempted": False,
             "resume_state": "ready" if resumable else "response_context_missing" if has_context else "context_missing"}
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


def clear_sessions(s, user):
    """Clear only this account's local transactions, never remote attendance."""
    from server.mail_delivery import cancel_pending
    rows = s.exec(select(SystemSetting).where(SystemSetting.tenant_id == user.tenant_id)
                  .where(SystemSetting.key.startswith(setting_storage_key(PREFIX, user.tenant_id)))).all()
    owned = [row for row in rows if (row.value or {}).get("user_id") == user.id]
    for row in owned:
        cancel_pending(s, user.tenant_id, verification_session_id=(row.value or {}).get("id"))
        s.delete(row)
    s.commit()
    return {"cleared": len(owned)}


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
        if value["state"] == "record_confirmed" or time.time() - value.get("last_checked", 0) < VERIFICATION_POLL_SECONDS:
            return public(value)
        from server.coreApi.MainLogicApi import ApiClient
        from server.user_runtime import user_to_config, runtime_login_valid
        from server.util.Config import ConfigManager
        config = user_to_config(user)
        if not runtime_login_valid(config.get("userInfo")):
            raise HTTPException(status_code=409, detail="工学云登录已过期，请先刷新登录状态")
        original_token = str((config.get("userInfo") or {}).get("token") or "")
        client = ApiClient(ConfigManager(config=config))
        value["last_checked"] = time.time()
        value["check_state"] = "checked"
        expired = time.time() >= value["expires_at"]
        # A 200/null response acknowledges this query, not the final attendance.
        # Keep querying while the transaction is pending: the user may finish
        # authorization after an earlier check. Only a confirmed record or TTL
        # ends checks; the shared polling throttle still prevents double clicks.
        if value["verification_type"] == "account" and not expired:
            try:
                payload = json.loads(decrypt_secret(value["payload"]))
                if not value.get("resume_attempted") and continuation_context_supported(payload.get("submission_context")):
                    value.update(has_submission_context=True, resume_state="ready")
                response = client.query_alipay_clockin_verification(payload["outRegisterNo"])
                # A successful queryAxdj may have a null body. Attendance must
                # still be independently confirmed below; never replay save.
                value["verification_confirmed"] = verification_query_succeeded(response)
            except Exception as exc:
                value["check_state"] = "verification_query_failed"
                if "过期" in str(exc):
                    expired = True
                    value["check_state"] = "verification_expired"
                elif str(exc).strip() in {"token失效", "Token失效", "token已失效", "登录已失效", "请重新登录"}:
                    value["check_state"] = "login_expired"
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
            # Read requests may renew a remotely-revoked token inside ApiClient.
            # Persist it or the next check reuses the stale token and logs in again.
            # Do not overwrite a newer session created concurrently elsewhere.
            updated_info = config.get("userInfo") or {}
            updated_token = str(updated_info.get("token") or "")
            stored_token = str((live_user.userInfo or {}).get("token") or "")
            if updated_token and updated_token != original_token and stored_token == original_token:
                live_user.userInfo = dict(updated_info)
                s.add(live_user)
            # Reload after the remote read: a background detector may already have confirmed it.
            current = dict(_owned(s, user, sid).value)
            if current.get("state") == "record_confirmed":
                s.commit()
                return public(current)
            # A concurrent continuation can outlive a lock lease. A stale read
            # must never erase its durable at-most-once claim or response state.
            if current.get("resume_attempted"):
                for key in ("resume_state", "resume_attempted", "resume_attempted_at"):
                    if key in current:
                        value[key] = current[key]
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


def resume_session(user, sid, *, db_engine=None):
    """Continue the original transaction at most once, not /check.

    Persist the claim BEFORE any write request. A crash, timeout or unknown
    response thereafter is read-only: absence of a record is not proof that a
    save was never received. Existing legacy sessions cannot be reconstructed.
    """
    from server.coreApi.MainLogicApi import ApiClient
    from server.user_runtime import user_to_config, runtime_login_valid
    from server.util.Config import ConfigManager
    db = db_engine if db_engine is not None else engine
    with Session(db) as s:
        value = dict(_owned(s, user, sid).value)
    token = acquire_task_lock(f"verification-check:{user.tenant_id}:{sid}", ttl_seconds=180, db_engine=db)
    if token is None:
        raise HTTPException(status_code=409, detail="本次授权正在处理，请稍后只检查记录")
    job_lock = None
    try:
        job_lock = acquire_task_lock(f"scheduler:user:{user.id}:clock_in:{value['target_type']}",
                                     ttl_seconds=180, db_engine=db)
        if job_lock is None:
            raise HTTPException(status_code=409, detail="签到任务正在执行，请稍后检查记录")
        tenant_id = user.tenant_id
        with Session(db) as s:
            user = s.get(User, user.id)
            if not user or user.tenant_id != tenant_id or user.deleted_at is not None:
                raise HTTPException(status_code=404, detail="账号不存在")
            s.expunge(user)
            value = dict(_owned(s, user, sid).value)
        if value.get("record_confirmed") or value.get("resume_attempted"):
            return public(value)
        if public(value)["state"] in TERMINAL:
            raise HTTPException(status_code=409, detail="授权事务已结束或过期，不能续提")
        if value.get("verification_type") != "account":
            raise HTTPException(status_code=409, detail="此验证类型不支持续提，请使用官方 App 检查考勤")
        try:
            payload = json.loads(decrypt_secret(value["payload"]))
        except (ValueError, TypeError, KeyError):
            raise HTTPException(status_code=409, detail="首次请求上下文无法解密")
        if not continuation_context_supported(payload.get("submission_context")):
            raise HTTPException(status_code=409, detail="缺少可用的首次请求或官方验证响应，不能安全续提；请使用官方 App 检查考勤")
        config = user_to_config(user)
        if not runtime_login_valid(config.get("userInfo")):
            raise HTTPException(status_code=409, detail="工学云登录已过期，请先刷新登录状态")
        original_token = str((config.get("userInfo") or {}).get("token") or "")
        client = ApiClient(ConfigManager(config=config))
        try:
            client.validate_clock_in_continuation(payload.get("submission_context"), payload.get("outRegisterNo"),
                                                  value["attendance_date"], value["target_type"])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        # A fresh read is mandatory even if the previous UI read was throttled.
        check = confirm_attendance(client, value["attendance_date"], value["target_type"], attempts=1)
        if not check["record_confirmed"]:
            if check["confirmation_state"] == "query_failed":
                raise HTTPException(status_code=409, detail="考勤回查失败，不能判断是否已签到；本次不续提")
            try:
                response = client.query_alipay_clockin_verification(payload["outRegisterNo"])
            except Exception:
                raise HTTPException(status_code=409, detail="官方未确认本次验证有效；本次不续提")
            if not verification_query_succeeded(response):
                raise HTTPException(status_code=409, detail="本次授权尚未确认；本次不续提")
            with Session(db) as s:
                # Row lock plus durable flag protects even after lease expiry.
                row = s.exec(select(SystemSetting).where(
                    SystemSetting.key == setting_storage_key(PREFIX + sid, user.tenant_id),
                    SystemSetting.tenant_id == user.tenant_id).with_for_update()).first()
                if not row or (row.value or {}).get("user_id") != user.id:
                    raise HTTPException(status_code=404, detail="授权事务不存在")
                current = dict(row.value)
                if current.get("resume_attempted") or public(current).get("state") in TERMINAL:
                    return public(current)
                value = {**current, "has_submission_context": True, "resume_attempted": True, "resume_attempted_at": time.time(),
                         "resume_state": "uncertain", "verification_confirmed": True,
                         "state": "verified_pending_record", "updated_at": time.time()}
                upsert_setting(s, PREFIX + sid, value, user.tenant_id)
                s.commit()
            try:
                value["resume_state"] = client.resume_clock_in_submission(
                    payload["submission_context"], payload["outRegisterNo"], value["attendance_date"], value["target_type"])
            except Exception:
                # No raw exception: transport errors can include sensitive data.
                value["resume_state"] = "uncertain"
            check = confirm_attendance(client, value["attendance_date"], value["target_type"], attempts=3, delay=0.5)
        if check["record_confirmed"]:
            value.update(state="record_confirmed", record_confirmed=True, payload="", server_time=check["server_time"])
        value.update(last_checked=time.time(), updated_at=time.time(), check_state="checked")
        if check["confirmation_state"] == "query_failed":
            value["check_state"] = "record_query_failed"
        with Session(db) as s:
            current = dict(_owned(s, user, sid).value)
            if current.get("state") == "record_confirmed":
                return public(current)
            upsert_setting(s, PREFIX + sid, value, user.tenant_id)
            live = s.get(User, user.id)
            updated_info = config.get("userInfo") or {}
            if live and str((live.userInfo or {}).get("token") or "") == original_token and updated_info.get("token"):
                live.userInfo = dict(updated_info)
                s.add(live)
            if value["record_confirmed"]:
                from server.mail_delivery import cancel_pending
                cancel_pending(s, user.tenant_id, verification_session_id=sid)
            reconcile_user(s, live, value["attendance_date"], [{**check, "verification_confirmed": value["verification_confirmed"]}])
            s.commit()
        return public(value)
    finally:
        release_task_lock(job_lock, db_engine=db)
        release_task_lock(token, db_engine=db)


def process_pending_sessions(*, db_engine=None):
    """Detect completed authorization without requiring an open browser.

    /check stays read-only. Automatic continuation shares the explicit resume
    path's fresh official checks, locks and durable at-most-once claim.
    Include manually initiated sessions even when scheduled clock-in is off.
    """
    import logging
    from server.scheduler import _is_user_tenant_active
    db = db_engine if db_engine is not None else engine
    now = time.time()
    with Session(db) as s:
        rows = s.exec(select(SystemSetting).where(SystemSetting.key.contains(PREFIX))).all()
        pending = [(row.tenant_id, dict(row.value or {})) for row in rows
                   if (row.value or {}).get("state") not in TERMINAL
                   and (row.value or {}).get("expires_at", 0) > now
                   and now - (row.value or {}).get("last_checked", 0) >= VERIFICATION_POLL_SECONDS]
    for tenant_id, meta in pending:
        try:
            with Session(db) as s:
                user = s.get(User, meta.get("user_id"))
                if (not user or user.tenant_id != tenant_id or user.deleted_at is not None
                        or not _is_user_tenant_active(s, user)):
                    continue
                s.expunge(user)
            state = check_session(user, meta["id"], db_engine=db)
            if (state.get("verification_confirmed") and state.get("resume_available")
                    and state.get("check_state") == "checked"):
                resume_session(user, meta["id"], db_engine=db)
        except HTTPException as exc:
            # A busy lease or unavailable official check is retried by the next
            # scan, but a claimed write can never be sent again.
            logging.getLogger(__name__).debug("授权自动处理暂不可用 status=%s", exc.status_code)
        except Exception as exc:
            # Never log the encrypted context, registration or upstream body.
            logging.getLogger(__name__).error("授权自动处理失败 type=%s", type(exc).__name__)


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
