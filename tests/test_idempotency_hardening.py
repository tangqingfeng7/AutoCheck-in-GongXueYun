import unittest

from fastapi import HTTPException
from sqlmodel import SQLModel, create_engine


class IdempotencyHardeningTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        import server.models  # noqa: F401 - 在 create_all 前加载 SQLModel 元数据
        SQLModel.metadata.create_all(self.engine)

    def test_idempotency_claim_blocks_duplicates_and_replays_completed_response(self):
        from server.idempotency import claim_idempotency_record, finalize_idempotency_record, build_idempotency_request_hash

        request_hash = build_idempotency_request_hash({"ids": [1, 2], "concurrency": 2, "tenant_id": "default"})
        storage_key = "batch-run:test-20260529"

        self.assertIsNone(
            claim_idempotency_record(
                db_engine=self.engine,
                tenant_id="default",
                logical_key=storage_key,
                request_hash=request_hash,
            )
        )

        with self.assertRaises(HTTPException) as ctx:
            claim_idempotency_record(
                db_engine=self.engine,
                tenant_id="default",
                logical_key=storage_key,
                request_hash=request_hash,
            )
        self.assertEqual(ctx.exception.status_code, 409)

        finalize_idempotency_record(
            db_engine=self.engine,
            tenant_id="default",
            logical_key=storage_key,
            request_hash=request_hash,
            response={"ok": True, "job_id": 7},
        )

        self.assertEqual(
            claim_idempotency_record(
                db_engine=self.engine,
                tenant_id="default",
                logical_key=storage_key,
                request_hash=request_hash,
            ),
            {"ok": True, "job_id": 7},
        )

    def test_idempotency_claim_rejects_reused_key_with_different_payload(self):
        from server.idempotency import claim_idempotency_record, build_idempotency_request_hash

        storage_key = "manual-run:test-20260529"
        first_hash = build_idempotency_request_hash({"user_id": 1, "task": "run"})
        second_hash = build_idempotency_request_hash({"user_id": 2, "task": "run"})

        claim_idempotency_record(
            db_engine=self.engine,
            tenant_id="default",
            logical_key=storage_key,
            request_hash=first_hash,
        )

        with self.assertRaises(HTTPException) as ctx:
            claim_idempotency_record(
                db_engine=self.engine,
                tenant_id="default",
                logical_key=storage_key,
                request_hash=second_hash,
            )
        self.assertEqual(ctx.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
