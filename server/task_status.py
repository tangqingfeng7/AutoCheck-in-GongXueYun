import datetime as dt
import time
import uuid
import logging
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from server.models import User
from server.database import engine
from server.settings_store import get_setting, upsert_setting
from server.attendance_confirmation import confirm_attendance

TZ = ZoneInfo("Asia/Shanghai")


def due_targets(user, now):
    from server.scheduler import _get_schedule
    from server.util.HelperFunctions import is_holiday
    if not user.enable_clockin:
        return []
    schedule = _get_schedule(user)
    day = now.date()
    start = dt.date.fromisoformat(schedule["startDate"]) if schedule.get("startDate") else day
    total = schedule.get("totalDays")
    if day < start or (isinstance(total, int) and total > 0 and day >= start + dt.timedelta(days=total)):
        return []
    from server.clockin_preauthorization import parse_plan_end_date
    try:
        if day > parse_plan_end_date(user.planInfo):
            return []
    except ValueError:
        logging.getLogger(__name__).debug("实习计划结束日期不可用，按已配置日程检查")
    if day.isoweekday() not in schedule["weekdays"]:
        return []
    clock = user.clockIn or {}
    # Intentional rest/custom-day skips are not missed executions.
    if clock.get("mode") == "holiday" and is_holiday(now) and not clock.get("specialClockIn"):
        return []
    if clock.get("mode") == "custom" and day.isoweekday() not in (clock.get("customDays") or []) and not clock.get("specialClockIn"):
        return []
    import os
    jitter = min(3600, max(0, int(os.getenv("SCHEDULER_JITTER_SECONDS") or "600")))
    targets = []
    for kind, field in (("START", "startTime"), ("END", "endTime")):
        hh, mm = map(int, schedule[field].split(":"))
        due = dt.datetime.combine(day, dt.time(hh, mm), tzinfo=TZ)
        if now >= due + dt.timedelta(seconds=jitter + 300):
            targets.append(kind)
    return targets


def detect_user(user, now=None):
    from server.coreApi.MainLogicApi import ApiClient
    from server.util.Config import ConfigManager
    from server.scheduler import user_to_config
    from server.task_runner import _load_global_smtp_settings
    from server.pushplus_settings import load_global_pushplus
    from server.user_runtime import build_effective_push_notifications, runtime_login_valid
    from server.util.MessagePush import MessagePusher
    now = now or dt.datetime.now(TZ)
    targets = due_targets(user, now)
    if not targets:
        return
    key = f"attendance-monitor:{user.id}"
    with Session(engine) as s:
        row = get_setting(s, key, user.tenant_id)
        previous = dict(row.value) if row else {}
    if previous.get("day") == now.date().isoformat() and time.time() - previous.get("checked_at", 0) < 600:
        return
    config = user_to_config(user)
    client = ApiClient(ConfigManager(config=config))
    if not runtime_login_valid(config.get("userInfo")):
        # Read-only detector does not initiate authentication or CAPTCHAs.
        checks = [{"target_type": kind, "record_confirmed": False, "confirmation_state": "login_expired"} for kind in targets]
    else:
        checks = [confirm_attendance(client, now.date().isoformat(), kind, attempts=1) for kind in targets]
    day = now.date().isoformat()
    prior = {c.get("target_type"): c for c in previous.get("checks", [])} if previous.get("day") == day else {}
    for check in checks:
        old = prior.get(check["target_type"], {})
        for field in ("incident_id", "incident_active", "alert_pending", "recovery_pending", "notification_state"):
            if field in old:
                check[field] = old[field]
        if not check["record_confirmed"]:
            if not old.get("incident_active"):
                check.update(incident_id=uuid.uuid4().hex, incident_active=True,
                             alert_pending=True, recovery_pending=False, notification_state="pending_enqueue")
        elif old.get("incident_active"):
            check.update(incident_active=False, alert_pending=False, recovery_pending=True, notification_state="pending_enqueue")
    snapshot = {"day": day, "checked_at": time.time(), "checks": checks}
    with Session(engine) as s:
        from server.attendance_reconciliation import reconcile_user
        from server.verification_sessions import mark_confirmed
        live = s.get(User, user.id)
        if live and live.tenant_id == user.tenant_id and live.deleted_at is None:
            reconcile_user(s, live, day, checks)
            mark_confirmed(s, live, day, checks)
        from server.mail_delivery import cancel_pending
        for check in checks:
            if check.get("recovery_pending"):
                cancel_pending(s, user.tenant_id, incident_id=check.get("incident_id"))
        upsert_setting(s, key, snapshot, user.tenant_id); s.commit()
    smtp = build_effective_push_notifications(user_push=user.pushNotifications,
                                              smtp_settings=_load_global_smtp_settings(user.tenant_id),
                                              pushplus_settings=load_global_pushplus(user.tenant_id, db_engine=engine))
    for cfg in smtp:
        cfg["tenant_id"] = user.tenant_id
    for check in checks:
        recovery = check.get("recovery_pending", False)
        if not recovery and not check.get("alert_pending"):
            continue
        state = check["confirmation_state"]
        message = ("异常已恢复，服务端考勤记录已确认；没有重新提交签到" if recovery else
                   "计划时间已过，服务端未查到考勤记录，请手动检查；未自动补签" if state == "missing"
                   else "考勤查询不可用或登录过期，无法确认是否漏卡，请手动检查")
        delivered = MessagePusher(smtp).push([{"status": "success" if recovery else "fail",
                                  "task_type": "异常恢复通知" if recovery else "漏执行检测",
                                  "message": message, "details": {"日期": snapshot["day"],
                                  "类型": check["target_type"], "检测状态": state,
                                  "通知事件": check.get("incident_id")}}])
        smtp_states = [item.get("status") for item in delivered or [] if isinstance(item, dict) and item.get("type") in {"SMTP", "PushPlus", "ClawBot", "Server"}]
        if smtp_states:
            check["notification_state"] = smtp_states[-1]
        else:
            check["notification_state"] = "disabled"
        if any(status in {"sent", "provider_sent", "accepted", "queued", "retry", "sending", "uncertain"} for status in smtp_states):
            check["recovery_pending" if recovery else "alert_pending"] = False
    with Session(engine) as s:
        upsert_setting(s, key, snapshot, user.tenant_id); s.commit()


def detect_missed_executions():
    from server.scheduler import _iter_schedulable_users
    from server.execution_locks import acquire_task_lock, release_task_lock
    import logging
    from server.verification_sessions import cleanup_sessions
    cleanup_sessions()
    with Session(engine) as s:
        users = list(_iter_schedulable_users(s))
        for user in users:
            token = acquire_task_lock(f"attendance-monitor:{user.tenant_id}:{user.id}", ttl_seconds=300)
            if not token:
                continue
            try:
                detect_user(user)
            except Exception as exc:
                logging.getLogger(__name__).error("漏执行检测失败 user=%s type=%s", user.id, type(exc).__name__)
            finally:
                release_task_lock(token)


def status_snapshot(session, user):
    from server.scheduler import scheduler
    from server.mail_delivery import mail_status
    key = f"attendance-monitor:{user.id}"
    row = get_setting(session, key, user.tenant_id)
    jobs = []
    for kind in ("start", "end"):
        job = scheduler.get_job(f"user_{user.id}_{kind}")
        next_run = getattr(job, "next_run_time", None)
        jobs.append({"type": kind, "next_run": next_run.isoformat() if next_run else None})
    from server.user_runtime import sanitize_execution_results
    from server.verification_sessions import list_sessions
    import json
    from pathlib import Path
    watchdog = {"state": "unknown"}
    try:
        data = json.loads(Path("D:/Admin/gongxueyun/watchdog.json").read_text(encoding="utf-8-sig"))
        watchdog = {k: data.get(k) for k in ("state", "updated_at", "failures")}
        if time.time() - (data.get("updated_at") or 0) > 180:
            watchdog["state"] = "stale"
    except (OSError, ValueError) as exc:
        logging.getLogger(__name__).debug("保活状态读取不可用: %s", type(exc).__name__)
    return {"user_id": user.id, "scheduler_running": scheduler.running,
            "watchdog": watchdog,
            "enabled": user.enable_clockin, "jobs": jobs,
            "last_run": user.last_run_time, "last_status": user.last_status,
            "last_results": sanitize_execution_results(user.last_execution_result or []),
            "verification_sessions": list_sessions(session, user),
            "monitor": row.value if row else None, "mail": mail_status(session, user.tenant_id)}
