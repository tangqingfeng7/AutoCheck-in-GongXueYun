import datetime
import copy
import logging
import os
import random
import time
from typing import Any, Optional

from sqlalchemy import delete, event, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session as OrmSession
from sqlmodel import Session, select

from server.models import DEFAULT_TENANT_ID, AuditLog, BatchJob, BatchJobItem, HttpRequestMetric, TaskExecutionEvent, TaskExecutionLock
from server.request_context import get_request_id
from server.time_utils import utc_now

logger = logging.getLogger(__name__)
DEFAULT_HTTP_METRIC_RETENTION_DAYS = 14
DEFAULT_HTTP_METRIC_PURGE_INTERVAL_SECONDS = 3600
DEFAULT_HTTP_METRIC_EXCLUDED_PREFIXES = ("/assets/", "/favicon", "/healthz", "/readyz")
DEFAULT_RECENT_METRIC_WINDOW_SECONDS = 300
DEFAULT_METRICS_CACHE_TTL_SECONDS = 5
MAX_HTTP_METRIC_RETENTION_DAYS = 3650
_last_http_metric_purge_at = 0.0
_runtime_metrics_cache: dict[int, dict[str, Any]] = {}


def _engine(db_engine=None):
    if db_engine is not None:
        return db_engine
    from server.database import engine

    return engine


def _now_utc() -> datetime.datetime:
    return utc_now()


def _int_env(name: str, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default
    value = max(minimum, value)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _http_metric_retention_days() -> int:
    return _int_env(
        "HTTP_METRIC_RETENTION_DAYS",
        DEFAULT_HTTP_METRIC_RETENTION_DAYS,
        minimum=0,
        maximum=MAX_HTTP_METRIC_RETENTION_DAYS,
    )


def _http_metric_purge_interval_seconds() -> int:
    return _int_env(
        "HTTP_METRIC_PURGE_INTERVAL_SECONDS",
        DEFAULT_HTTP_METRIC_PURGE_INTERVAL_SECONDS,
        minimum=0,
    )


def _recent_metric_window_seconds() -> int:
    return _int_env("RECENT_METRIC_WINDOW_SECONDS", DEFAULT_RECENT_METRIC_WINDOW_SECONDS, minimum=60, maximum=86400)


def _metrics_cache_ttl_seconds() -> int:
    return _int_env("METRICS_CACHE_TTL_SECONDS", DEFAULT_METRICS_CACHE_TTL_SECONDS, minimum=0, maximum=3600)


def _clear_runtime_metrics_cache_for_bind(bind) -> None:
    if bind is None:
        _runtime_metrics_cache.clear()
        return
    engine = getattr(bind, "engine", None) if not isinstance(bind, Engine) else bind
    if engine is None:
        _runtime_metrics_cache.clear()
        return
    _runtime_metrics_cache.pop(id(engine), None)


def invalidate_runtime_metrics_cache(db_engine=None) -> None:
    _clear_runtime_metrics_cache_for_bind(_engine(db_engine))


def _after_session_commit(session) -> None:
    try:
        _clear_runtime_metrics_cache_for_bind(session.get_bind())
    except Exception:
        logger.debug("runtime metrics cache invalidation failed", exc_info=True)


event.listen(OrmSession, "after_commit", _after_session_commit)


def _split_env_list(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").replace(";", ",").split(",") if item.strip()]


def _http_metric_sample_rate() -> float:
    try:
        value = float(str(os.getenv("HTTP_METRIC_SAMPLE_RATE") or "1").strip())
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(value, 1.0))


def should_record_http_request_metric(path: str, status_code: int) -> bool:
    normalized_path = str(path or "/")
    prefixes = list(DEFAULT_HTTP_METRIC_EXCLUDED_PREFIXES)
    prefixes.extend(_split_env_list(os.getenv("HTTP_METRIC_EXCLUDE_PATH_PREFIXES") or ""))
    if any(normalized_path == prefix.rstrip("/") or normalized_path.startswith(prefix) for prefix in prefixes):
        return False
    if int(status_code or 0) >= 500:
        return True
    sample_rate = _http_metric_sample_rate()
    if sample_rate >= 1:
        return True
    if sample_rate <= 0:
        return False
    return random.random() < sample_rate


def purge_old_http_request_metrics(
    *,
    retention_days: Optional[int] = None,
    now: Optional[datetime.datetime] = None,
    db_engine=None,
) -> int:
    days = _http_metric_retention_days() if retention_days is None else max(0, int(retention_days))
    if days <= 0:
        return 0
    cutoff = (now or _now_utc()) - datetime.timedelta(days=days)
    try:
        with Session(_engine(db_engine)) as session:
            result = session.execute(delete(HttpRequestMetric).where(HttpRequestMetric.created_at < cutoff))
            session.commit()
            return int(result.rowcount or 0)
    except Exception as exc:
        logger.debug("purge old http request metrics failed: %s", exc)
        return 0


def _maybe_purge_http_request_metrics(*, db_engine=None) -> None:
    global _last_http_metric_purge_at
    interval = _http_metric_purge_interval_seconds()
    if interval <= 0:
        return
    now_monotonic = time.monotonic()
    if now_monotonic - _last_http_metric_purge_at < interval:
        return
    _last_http_metric_purge_at = now_monotonic
    purge_old_http_request_metrics(db_engine=db_engine)


def record_task_event(
    *,
    source: str,
    event: str,
    task_key: str,
    user_id: Optional[int] = None,
    status: Optional[str] = None,
    duration_ms: Optional[int] = None,
    error: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
    db_engine=None,
) -> None:
    try:
        with Session(_engine(db_engine)) as session:
            session.add(
                TaskExecutionEvent(
                    source=str(source or "unknown"),
                    event=str(event or "event"),
                    task_key=str(task_key or "unknown"),
                    user_id=user_id,
                    status=status,
                    request_id=request_id or get_request_id() or None,
                    duration_ms=duration_ms,
                    error=(str(error)[:1000] if error else None),
                    detail=detail or {},
                )
            )
            session.commit()
    except Exception as exc:
        logger.debug("record task event failed: %s", exc)


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    request_id: Optional[str] = None,
    tenant_id: str = DEFAULT_TENANT_ID,
    db_engine=None,
) -> None:
    if not should_record_http_request_metric(path, status_code):
        return
    try:
        with Session(_engine(db_engine)) as session:
            session.add(
                HttpRequestMetric(
                    tenant_id=tenant_id or DEFAULT_TENANT_ID,
                    method=str(method or "GET").upper()[:16],
                    path=str(path or "/")[:500],
                    status_code=int(status_code or 0),
                    request_id=(request_id or get_request_id() or None),
                    duration_ms=max(0, int(duration_ms or 0)),
                )
            )
            session.commit()
        _maybe_purge_http_request_metrics(db_engine=db_engine)
    except Exception as exc:
        logger.debug("record http request metric failed: %s", exc)


def _counts(session: Session, model, column) -> dict[str, int]:
    rows = session.exec(select(column, func.count()).select_from(model).group_by(column)).all()
    return {str(key): int(count or 0) for key, count in rows if key is not None}


def _status_bucket(status_code: int) -> str:
    if status_code < 100:
        return "unknown"
    return f"{int(status_code / 100)}xx"


def _http_status_counts(session: Session, *, since: Optional[datetime.datetime] = None) -> tuple[int, dict[str, int]]:
    query = select(HttpRequestMetric.status_code, func.count()).group_by(HttpRequestMetric.status_code)
    if since is not None:
        query = query.where(HttpRequestMetric.created_at >= since)
    rows = session.exec(query).all()
    by_status: dict[str, int] = {}
    total = 0
    for status_code, count in rows:
        bucket = _status_bucket(int(status_code or 0))
        by_status[bucket] = by_status.get(bucket, 0) + int(count or 0)
        total += int(count or 0)
    return total, by_status


def _http_request_metrics(session: Session, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    total, by_status = _http_status_counts(session)
    recent_cutoff = (now or _now_utc()) - datetime.timedelta(seconds=_recent_metric_window_seconds())
    recent_total, recent_by_status = _http_status_counts(session, since=recent_cutoff)

    return_metrics: dict[str, Any] = {
        "total": total,
        "by_status": by_status,
        "recent_total": recent_total,
        "recent_by_status": recent_by_status,
        "by_method": _counts(session, HttpRequestMetric, HttpRequestMetric.method),
    }

    latency = session.exec(
        select(
            func.min(HttpRequestMetric.duration_ms),
            func.max(HttpRequestMetric.duration_ms),
            func.avg(HttpRequestMetric.duration_ms),
        )
    ).one()
    min_latency, max_latency, avg_latency = latency
    last_request_id = session.exec(
        select(HttpRequestMetric.request_id)
        .where(HttpRequestMetric.request_id.is_not(None))
        .order_by(HttpRequestMetric.id.desc())
        .limit(1)
    ).first()
    return_metrics.update(
        {
            "last_request_id": last_request_id,
            "latency_ms": {
                "min": int(min_latency or 0),
                "max": int(max_latency or 0),
                "avg": round(float(avg_latency or 0), 2),
            },
        }
    )
    return return_metrics


def _auth_failure_counts(
    session: Session,
    *,
    actions: tuple[str, ...],
    since: Optional[datetime.datetime] = None,
) -> dict[str, int]:
    query = (
        select(AuditLog.action, func.count())
        .where(AuditLog.action.in_(actions))
        .group_by(AuditLog.action)
    )
    if since is not None:
        query = query.where(AuditLog.created_at >= since)
    rows = session.exec(query).all()
    return {str(action): int(count or 0) for action, count in rows if action is not None}


def _auth_failure_metrics(session: Session, *, now: Optional[datetime.datetime] = None) -> dict[str, Any]:
    actions = ("auth.login.failed", "app.login.failed")
    recent_cutoff = (now or _now_utc()) - datetime.timedelta(seconds=_recent_metric_window_seconds())
    return {
        "by_action": _auth_failure_counts(session, actions=actions),
        "recent_by_action": _auth_failure_counts(session, actions=actions, since=recent_cutoff),
    }


def _runtime_metrics_snapshot(*, db_engine=None) -> dict[str, Any]:
    now = _now_utc()
    with Session(_engine(db_engine)) as session:
        last_task_request_id = session.exec(
            select(TaskExecutionEvent.request_id)
            .where(TaskExecutionEvent.request_id.is_not(None))
            .order_by(TaskExecutionEvent.id.desc())
            .limit(1)
        ).first()
        active_locks = session.exec(
            select(func.count()).select_from(TaskExecutionLock).where(TaskExecutionLock.expires_at > now)
        ).one()
        return {
            "generated_at": now.isoformat(timespec="seconds") + "Z",
            "task_events": {
                "by_status": _counts(session, TaskExecutionEvent, TaskExecutionEvent.status),
                "by_source": _counts(session, TaskExecutionEvent, TaskExecutionEvent.source),
                "last_request_id": last_task_request_id,
            },
            "auth_failures": _auth_failure_metrics(session, now=now),
            "batch_jobs": {
                "by_status": _counts(session, BatchJob, BatchJob.status),
            },
            "batch_items": {
                "by_status": _counts(session, BatchJobItem, BatchJobItem.status),
            },
            "http_requests": _http_request_metrics(session, now=now),
            "locks": {
                "active": int(active_locks or 0),
            },
        }


def runtime_metrics(*, db_engine=None) -> dict[str, Any]:
    engine = _engine(db_engine)
    ttl_seconds = _metrics_cache_ttl_seconds()
    cache_key = id(engine)
    now_monotonic = time.monotonic()
    cache_entry = _runtime_metrics_cache.get(cache_key)
    if (
        ttl_seconds > 0
        and cache_entry
        and cache_entry.get("engine") is engine
        and now_monotonic - float(cache_entry.get("cached_at") or 0) < ttl_seconds
    ):
        return copy.deepcopy(cache_entry["metrics"])

    metrics = _runtime_metrics_snapshot(db_engine=engine)
    if ttl_seconds > 0:
        _runtime_metrics_cache[cache_key] = {
            "engine": engine,
            "cached_at": now_monotonic,
            "metrics": copy.deepcopy(metrics),
        }
    else:
        _runtime_metrics_cache.pop(cache_key, None)
    return metrics


def _prom_label_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _append_metric(lines: list[str], name: str, value: int | float, labels: Optional[dict[str, str]] = None) -> None:
    label_text = ""
    if labels:
        label_text = "{" + ",".join(f'{key}="{_prom_label_value(val)}"' for key, val in sorted(labels.items())) + "}"
    lines.append(f"{name}{label_text} {value}")


def prometheus_metrics_text(*, db_engine=None) -> str:
    metrics = runtime_metrics(db_engine=db_engine)
    lines = [
        "# HELP automoguding_task_events_total Task execution event snapshot grouped by status.",
        "# TYPE automoguding_task_events_total gauge",
    ]
    for status, count in sorted(metrics.get("task_events", {}).get("by_status", {}).items()):
        _append_metric(lines, "automoguding_task_events_total", int(count), {"status": status})

    lines.extend(
        [
            "# HELP automoguding_task_events_by_source_total Task execution events grouped by source.",
            "# TYPE automoguding_task_events_by_source_total gauge",
        ]
    )
    for source, count in sorted(metrics.get("task_events", {}).get("by_source", {}).items()):
        _append_metric(lines, "automoguding_task_events_by_source_total", int(count), {"source": source})

    lines.extend(
        [
            "# HELP automoguding_auth_failures_total Authentication failures grouped by action.",
            "# TYPE automoguding_auth_failures_total gauge",
        ]
    )
    for action, count in sorted(metrics.get("auth_failures", {}).get("by_action", {}).items()):
        _append_metric(lines, "automoguding_auth_failures_total", int(count), {"action": action})

    lines.extend(
        [
            "# HELP automoguding_auth_failures_recent_total Authentication failures grouped by action over the recent metric window.",
            "# TYPE automoguding_auth_failures_recent_total gauge",
        ]
    )
    for action, count in sorted(metrics.get("auth_failures", {}).get("recent_by_action", {}).items()):
        _append_metric(lines, "automoguding_auth_failures_recent_total", int(count), {"action": action})

    lines.extend(
        [
            "# HELP automoguding_batch_jobs_total Batch jobs grouped by status.",
            "# TYPE automoguding_batch_jobs_total gauge",
        ]
    )
    for status, count in sorted(metrics.get("batch_jobs", {}).get("by_status", {}).items()):
        _append_metric(lines, "automoguding_batch_jobs_total", int(count), {"status": status})

    lines.extend(
        [
            "# HELP automoguding_batch_items_total Batch job items grouped by status.",
            "# TYPE automoguding_batch_items_total gauge",
        ]
    )
    for status, count in sorted(metrics.get("batch_items", {}).get("by_status", {}).items()):
        _append_metric(lines, "automoguding_batch_items_total", int(count), {"status": status})

    lines.extend(
        [
            "# HELP automoguding_http_requests_total HTTP requests grouped by status class.",
            "# TYPE automoguding_http_requests_total gauge",
        ]
    )
    for status, count in sorted(metrics.get("http_requests", {}).get("by_status", {}).items()):
        _append_metric(lines, "automoguding_http_requests_total", int(count), {"status": status})

    lines.extend(
        [
            "# HELP automoguding_http_requests_recent_total HTTP requests grouped by status class over the recent metric window.",
            "# TYPE automoguding_http_requests_recent_total gauge",
        ]
    )
    for status, count in sorted(metrics.get("http_requests", {}).get("recent_by_status", {}).items()):
        _append_metric(lines, "automoguding_http_requests_recent_total", int(count), {"status": status})

    lines.extend(
        [
            "# HELP automoguding_http_request_latency_ms HTTP request latency in milliseconds.",
            "# TYPE automoguding_http_request_latency_ms gauge",
        ]
    )
    for key, value in sorted(metrics.get("http_requests", {}).get("latency_ms", {}).items()):
        _append_metric(lines, "automoguding_http_request_latency_ms", float(value), {"stat": key})

    lines.extend(
        [
            "# HELP automoguding_locks_active Active task execution locks.",
            "# TYPE automoguding_locks_active gauge",
        ]
    )
    _append_metric(lines, "automoguding_locks_active", int(metrics.get("locks", {}).get("active", 0)))
    return "\n".join(lines) + "\n"
