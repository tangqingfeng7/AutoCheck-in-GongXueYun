import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select


class RateLimitBucketBackendTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        import server.models  # noqa: F401 - 在 create_all 前加载 SQLModel 元数据

        SQLModel.metadata.create_all(self.engine)

    def test_database_rate_limit_uses_single_bucket_row_per_key(self):
        from server.models import RateLimitBucket, RateLimitEvent
        from server.rate_limit import check_rate_limit

        with patch.dict("os.environ", {"RATE_LIMIT_BACKEND": "database"}, clear=False):
            with patch("server.database.engine", self.engine):
                check_rate_limit("login:1.2.3.4", limit=2, per_seconds=60)
                check_rate_limit("login:1.2.3.4", limit=2, per_seconds=60)
                with self.assertRaises(HTTPException):
                    check_rate_limit("login:1.2.3.4", limit=2, per_seconds=60)

        with Session(self.engine) as session:
            buckets = session.exec(select(RateLimitBucket)).all()
            events = session.exec(select(RateLimitEvent)).all()

        self.assertEqual(len(buckets), 1)
        self.assertEqual(buckets[0].bucket_key, "login:1.2.3.4")
        self.assertEqual(buckets[0].count, 2)
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
