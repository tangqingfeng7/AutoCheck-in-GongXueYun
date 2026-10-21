import datetime as dt
import hashlib
import smtplib
import ssl
import time
from email import policy, message_from_string
from email.utils import formatdate

from sqlmodel import Session, select
from sqlalchemy import update

from server.database import engine
from server.execution_locks import acquire_task_lock, release_task_lock
from server.models import SystemSetting
from server.secret_store import encrypt_secret, decrypt_secret
from server.settings_store import get_setting, upsert_setting, setting_storage_key

PREFIX = "mail-outbox:"
DELAYS = (10, 30, 90)
RETENTION = 7 * 86400


def enqueue_and_send(config, message):
    tenant = str(config.get("tenant_id") or "default")
    # MIME boundaries change on serialization; derive dedup key from stable decoded parts.
    identity = str(message["To"]) + str(message["Subject"]) + dt.datetime.now(dt.timezone.utc).date().isoformat()
    identity += str(config.get("delivery_nonce") or "")
    identity += "".join(str(p.get_payload(decode=True)) for p in message.walk() if not p.is_multipart())
    key = PREFIX + hashlib.sha256(identity.encode()).hexdigest()
    token = acquire_task_lock(key, ttl_seconds=300, db_engine=engine)
    if token is None:
        return "busy"
    try:
        with Session(engine) as s:
            existing = get_setting(s, key, tenant)
            if existing:
                return existing.value.get("status", "unknown")
            message["Date"] = formatdate(localtime=False)
            message["Message-ID"] = f"<{key.split(':')[-1]}@gongxueyun.local>"
            encrypted = encrypt_secret(message.as_string(policy=policy.SMTP))
            if not encrypted.startswith("enc$"):
                raise ValueError("邮件队列需要配置加密密钥")
            now = time.time()
            value = {"status": "queued", "attempts": 0, "created_at": now,
                     "updated_at": now, "next_attempt": now, "payload": encrypted,
                     "expires_at": now + (1800 if message.get_content_subtype() == "related" else 86400)}
            for field in ("incident_id", "incident_phase", "verification_session_id"):
                if config.get(field):
                    value[field] = config[field]
            upsert_setting(s, key, value, tenant)
            s.commit()
        return _send(key, tenant, config)
    finally:
        release_task_lock(token, db_engine=engine)


def _send(key, tenant, config):
    with Session(engine) as s:
        row = s.exec(select(SystemSetting).where(SystemSetting.key == setting_storage_key(key, tenant)).with_for_update()).one()
        value = dict(row.value)
        # A crash after DATA may already have delivered: never automatically replay it.
        if value["status"] == "sending":
            value.update(status="uncertain", error="发送过程被中断，请检查收件箱")
            upsert_setting(s, key, value, tenant); s.commit()
            return "uncertain"
        if value["status"] not in {"queued", "retry"}:
            return value["status"]
        if time.time() < value["next_attempt"]:
            return value["status"]
        if time.time() >= value["expires_at"]:
            value.update(status="expired", payload="", error="通知已过期，不发送旧授权链接")
            upsert_setting(s, key, value, tenant); s.commit()
            return "expired"
        value.update(status="sending", attempts=value["attempts"] + 1, updated_at=time.time())
        upsert_setting(s, key, value, tenant); s.commit()
    phase = "connect"
    try:
        message = message_from_string(decrypt_secret(value["payload"]), policy=policy.SMTP)
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=20, context=ssl.create_default_context()) as smtp:
            smtp.login(config["username"], config["password"])
            phase = "data"
            refused = smtp.send_message(message)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
            # QUIT failure after acceptance must not cause a resend.
            phase = "accepted"
        status, error = "sent", ""
    except Exception as exc:
        code = getattr(exc, "smtp_code", 0) or 0
        permanent = isinstance(exc, (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, ValueError)) or code >= 500
        uncertain = phase == "data" and not permanent and not isinstance(exc, smtplib.SMTPResponseException)
        status = ("sent" if phase == "accepted" else "uncertain" if uncertain else
                  "failed" if permanent or value["attempts"] > len(DELAYS) else "retry")
        # Exception strings can contain recipients or auth challenges. Store only type/code.
        error = "" if status == "sent" else f"{type(exc).__name__}:{code}"
    value.update(status=status, error=error, updated_at=time.time())
    if status == "retry":
        value["next_attempt"] = time.time() + DELAYS[value["attempts"] - 1]
    elif status in {"sent", "failed", "uncertain"}:
        value["payload"] = ""
    with Session(engine) as s:
        upsert_setting(s, key, value, tenant); s.commit()
    return status


def process_outbox():
    from server.task_runner import _load_global_smtp_settings
    with Session(engine) as s:
        rows = s.exec(select(SystemSetting).where(SystemSetting.key.contains(PREFIX))).all()
        pending = []
        for row in rows:
            value = row.value or {}
            if time.time() - value.get("created_at", time.time()) > RETENTION:
                s.delete(row)
            elif value.get("status") in {"queued", "retry", "sending"}:
                pending.append((row.tenant_id, row.key.split(PREFIX, 1)[-1]))
        s.commit()
    for tenant, suffix in pending[:100]:
        key = PREFIX + suffix
        token = acquire_task_lock(key, ttl_seconds=300, db_engine=engine)
        if not token:
            continue
        try:
            cfg = _load_global_smtp_settings(tenant)
            if cfg.get("enabled"):
                _send(key, tenant, cfg)
        finally:
            release_task_lock(token, db_engine=engine)


def mail_status(session, tenant):
    rows = session.exec(select(SystemSetting).where(SystemSetting.tenant_id == tenant)
                        .where(SystemSetting.key.contains(PREFIX))).all()
    return [{k: v for k, v in (row.value or {}).items()
             if k in {"status", "attempts", "created_at", "updated_at", "next_attempt", "error"}}
            for row in sorted(rows, key=lambda r: (r.value or {}).get("updated_at", 0), reverse=True)[:20]]


def cancel_pending(session, tenant, *, incident_id=None, verification_session_id=None):
    """Only unsent queued/retry notices can be cancelled; never interrupt DATA."""
    if not incident_id and not verification_session_id:
        return
    rows = session.exec(select(SystemSetting).where(SystemSetting.tenant_id == tenant)
                        .where(SystemSetting.key.contains(PREFIX))).all()
    for row in rows:
        value = dict(row.value or {})
        match = (incident_id and value.get("incident_id") == incident_id and value.get("incident_phase") == "alert") or (
            verification_session_id and value.get("verification_session_id") == verification_session_id)
        if match and value.get("status") in {"queued", "retry"}:
            session.exec(update(SystemSetting).where(SystemSetting.key == row.key)
                         .where(SystemSetting.value["status"].as_string().in_(["queued", "retry"]))
                         .values(value={**value, "status": "cancelled", "payload": "", "updated_at": time.time()})
                         .execution_options(synchronize_session=False))
