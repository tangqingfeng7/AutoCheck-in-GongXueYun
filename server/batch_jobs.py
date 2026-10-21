import datetime
import secrets
from typing import Iterable

from sqlalchemy import func, update
from sqlmodel import Session, select

from server.models import BatchJobItem
from server.time_utils import utc_now


def get_batch_job_item_status_counts(
    session: Session,
    job_id: int,
    statuses: Iterable[str] | None = None,
) -> dict[str, int]:
    stmt = select(BatchJobItem.status, func.count()).where(BatchJobItem.job_id == job_id)
    if statuses is not None:
        status_list = [str(item) for item in statuses]
        if not status_list:
            return {}
        stmt = stmt.where(BatchJobItem.status.in_(status_list))
    rows = session.exec(stmt.group_by(BatchJobItem.status)).all()
    return {str(status): int(count or 0) for status, count in rows}


def count_batch_job_items_by_status(session: Session, job_id: int, status: str) -> int:
    return get_batch_job_item_status_counts(session, job_id, [status]).get(status, 0)


def claim_batch_job_items(
    session: Session,
    job_id: int,
    capacity: int,
    now: datetime.datetime | None = None,
    owner: str | None = None,
    lease_seconds: int | None = None,
    return_claims: bool = False,
) -> list:
    if capacity <= 0:
        return []
    current = now or utc_now()
    worker_owner = str(owner or "queue-worker")
    lease_seconds = max(1, int(lease_seconds or 1800))
    candidate_ids = session.exec(
        select(BatchJobItem.id)
        .where(
            (BatchJobItem.job_id == job_id)
            & (BatchJobItem.status == "queued")
            & ((BatchJobItem.next_run_at.is_(None)) | (BatchJobItem.next_run_at <= current))
        )
        .order_by(BatchJobItem.id.asc())
        .limit(capacity)
    ).all()

    claimed: list = []
    for item_id in candidate_ids:
        if item_id is None:
            continue
        lock_token = secrets.token_urlsafe(24)
        result = session.exec(
            update(BatchJobItem)
            .where((BatchJobItem.id == int(item_id)) & (BatchJobItem.status == "queued"))
            .values(
                status="running",
                started_at=current,
                locked_by=worker_owner,
                lock_token=lock_token,
                heartbeat_at=current,
                lease_until=current + datetime.timedelta(seconds=lease_seconds),
            )
        )
        if int(getattr(result, "rowcount", 0) or 0) == 1:
            if return_claims:
                claimed.append({"item_id": int(item_id), "lock_token": lock_token})
            else:
                claimed.append(int(item_id))
    session.commit()
    return claimed
