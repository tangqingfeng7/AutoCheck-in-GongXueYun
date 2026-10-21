import datetime
import unittest

from sqlmodel import Session, SQLModel, create_engine

from server.models import BatchJob, BatchJobItem


class QueueWorkerReclaimTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)

    def test_stale_running_item_is_requeued_with_backoff(self):
        from server.queue_worker import reclaim_stale_running_items

        now = datetime.datetime(2026, 5, 28, 12, 0, 0)
        started_at = now - datetime.timedelta(minutes=10)
        with Session(self.engine) as session:
            job = BatchJob(created_by="test", status="running", total=1, concurrency=1, user_ids=[1])
            session.add(job)
            session.commit()
            session.refresh(job)
            item = BatchJobItem(
                job_id=job.id,
                user_id=1,
                status="running",
                started_at=started_at,
                attempts=1,
                max_attempts=3,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            item_id = item.id

        reclaimed = reclaim_stale_running_items(db_engine=self.engine, now=now, timeout_seconds=60)

        with Session(self.engine) as session:
            item = session.get(BatchJobItem, item_id)

        self.assertEqual(reclaimed, 1)
        self.assertEqual(item.status, "queued")
        self.assertIsNone(item.started_at)
        self.assertIsNone(item.finished_at)
        self.assertIsNotNone(item.next_run_at)
        self.assertIn("Timed out", item.error)

    def test_stale_running_item_fails_when_attempts_are_exhausted(self):
        from server.queue_worker import reclaim_stale_running_items

        now = datetime.datetime(2026, 5, 28, 12, 0, 0)
        started_at = now - datetime.timedelta(minutes=10)
        with Session(self.engine) as session:
            job = BatchJob(created_by="test", status="running", total=1, concurrency=1, user_ids=[1])
            session.add(job)
            session.commit()
            session.refresh(job)
            item = BatchJobItem(
                job_id=job.id,
                user_id=1,
                status="running",
                started_at=started_at,
                attempts=3,
                max_attempts=3,
            )
            session.add(item)
            session.commit()
            session.refresh(job)
            session.refresh(item)
            job_id = job.id
            item_id = item.id

        reclaimed = reclaim_stale_running_items(db_engine=self.engine, now=now, timeout_seconds=60)

        with Session(self.engine) as session:
            job = session.get(BatchJob, job_id)
            item = session.get(BatchJobItem, item_id)

        self.assertEqual(reclaimed, 1)
        self.assertEqual(item.status, "fail")
        self.assertEqual(item.finished_at, now)
        self.assertEqual(job.completed, 1)
        self.assertEqual(job.fail, 1)
        self.assertEqual(job.status, "done")
        self.assertEqual(job.finished_at, now)


if __name__ == "__main__":
    unittest.main()
