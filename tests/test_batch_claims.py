import unittest

from sqlmodel import Session, SQLModel, create_engine

from server.models import BatchJob, BatchJobItem


class BatchClaimTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)

    def test_claim_batch_job_items_never_returns_already_running_items(self):
        from server.batch_jobs import claim_batch_job_items

        with Session(self.engine) as session:
            job = BatchJob(created_by="test", total=2, concurrency=1, user_ids=[1, 2])
            session.add(job)
            session.commit()
            session.refresh(job)
            session.add(BatchJobItem(job_id=job.id, user_id=1, status="queued"))
            session.add(BatchJobItem(job_id=job.id, user_id=2, status="queued"))
            session.commit()

            first = claim_batch_job_items(session, job.id, capacity=1)
            second = claim_batch_job_items(session, job.id, capacity=2)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(first[0], second[0])


if __name__ == "__main__":
    unittest.main()
