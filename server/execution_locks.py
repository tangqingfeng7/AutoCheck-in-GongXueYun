import datetime
import os
import socket
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Optional

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from server.models import TaskExecutionLock
from server.time_utils import utc_now


@dataclass(frozen=True)
class TaskLockToken:
    lock_key: str
    owner: str
    expires_at: datetime.datetime


def _now_utc() -> datetime.datetime:
    return utc_now()


def _default_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex}"


def _engine(db_engine=None):
    if db_engine is not None:
        return db_engine
    from server.database import engine

    return engine


def acquire_task_lock(
    lock_key: str,
    *,
    ttl_seconds: int = 1800,
    owner: Optional[str] = None,
    now: Optional[datetime.datetime] = None,
    db_engine=None,
    detail: Optional[dict] = None,
) -> Optional[TaskLockToken]:
    key = str(lock_key or "").strip()
    if not key:
        raise ValueError("lock_key is required")
    ttl = max(1, int(ttl_seconds or 1))
    current = now or _now_utc()
    expires_at = current + datetime.timedelta(seconds=ttl)
    token = TaskLockToken(lock_key=key, owner=owner or _default_owner(), expires_at=expires_at)

    with Session(_engine(db_engine)) as session:
        try:
            session.add(
                TaskExecutionLock(
                    lock_key=token.lock_key,
                    owner=token.owner,
                    acquired_at=current,
                    expires_at=token.expires_at,
                    detail=detail or {},
                )
            )
            session.commit()
            return token
        except IntegrityError:
            session.rollback()

        result = session.exec(
            update(TaskExecutionLock)
            .where(TaskExecutionLock.lock_key == token.lock_key)
            .where(TaskExecutionLock.expires_at <= current)
            .values(
                owner=token.owner,
                acquired_at=current,
                expires_at=token.expires_at,
                detail=detail or {},
            )
        )
        if int(getattr(result, "rowcount", 0) or 0) == 1:
            session.commit()
            return token
        session.rollback()
        return None


def release_task_lock(token: TaskLockToken | None, *, db_engine=None) -> bool:
    if token is None:
        return False
    with Session(_engine(db_engine)) as session:
        result = session.exec(
            delete(TaskExecutionLock).where(
                (TaskExecutionLock.lock_key == token.lock_key)
                & (TaskExecutionLock.owner == token.owner)
            )
        )
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0) == 1


@contextmanager
def task_execution_lock(
    lock_key: str,
    *,
    ttl_seconds: int = 1800,
    owner: Optional[str] = None,
    db_engine=None,
    detail: Optional[dict] = None,
) -> Iterator[Optional[TaskLockToken]]:
    token = acquire_task_lock(
        lock_key,
        ttl_seconds=ttl_seconds,
        owner=owner,
        db_engine=db_engine,
        detail=detail,
    )
    try:
        yield token
    finally:
        if token is not None:
            release_task_lock(token, db_engine=db_engine)
