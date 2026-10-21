import datetime
import unittest

from sqlmodel import Session, SQLModel, create_engine, select


class SettingsObservabilityHardeningTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        import server.models  # noqa: F401 - 在 create_all 前加载 SQLModel 元数据

        SQLModel.metadata.create_all(self.engine)

    def test_settings_store_keeps_tenants_isolated(self):
        from server.models import SystemSetting
        from server.settings_store import get_setting, setting_storage_key, upsert_setting

        with Session(self.engine) as session:
            upsert_setting(session, "notifications", {"smtp": {"from": "default"}}, tenant_id="default")
            upsert_setting(session, "notifications", {"smtp": {"from": "acme"}}, tenant_id="acme")
            session.commit()

            default_row = get_setting(session, "notifications", tenant_id="default")
            acme_row = get_setting(session, "notifications", tenant_id="acme")
            rows = session.exec(select(SystemSetting)).all()

        self.assertEqual(setting_storage_key("notifications", "default"), "notifications")
        self.assertEqual(setting_storage_key("notifications", "acme"), "acme:notifications")
        self.assertEqual(default_row.value["smtp"]["from"], "default")
        self.assertEqual(acme_row.value["smtp"]["from"], "acme")
        self.assertEqual(len(rows), 2)

    def test_proxy_settings_update_uses_admin_tenant_scope(self):
        from server import api
        from server.models import SystemSetting
        from server.settings_store import get_setting

        with Session(self.engine) as session:
            api.update_proxy_settings(
                session=session,
                admin={"sub": "admin", "tenant_id": "acme"},
                req=api.ProxySettingsUpdateRequest(proxy={"enabled": True, "proxyUrls": "http://proxy.acme:8080"}),
            )
            acme_row = get_setting(session, "moguding_proxy", tenant_id="acme")
            default_row = get_setting(session, "moguding_proxy", tenant_id="default")
            setting_rows = session.exec(select(SystemSetting).where(SystemSetting.key == "acme:moguding_proxy")).all()

        self.assertIsNotNone(acme_row)
        self.assertIsNone(default_row)
        self.assertEqual(acme_row.value["proxyUrls"], "http://proxy.acme:8080")
        self.assertEqual(len(setting_rows), 1)

    def test_external_error_detail_does_not_expose_exception_text(self):
        from server.http_client import safe_external_error_detail

        detail = safe_external_error_detail("地理搜索失败", RuntimeError("token=secret-internal-url"))

        self.assertEqual(detail, "地理搜索失败")
        self.assertNotIn("secret-internal-url", detail)

    def test_http_metric_retention_purges_old_rows(self):
        from server.models import HttpRequestMetric
        from server.observability import purge_old_http_request_metrics

        now = datetime.datetime(2026, 5, 28, tzinfo=datetime.timezone.utc)
        with Session(self.engine) as session:
            session.add(
                HttpRequestMetric(
                    method="GET",
                    path="/old",
                    status_code=200,
                    duration_ms=1,
                    created_at=now - datetime.timedelta(days=10),
                )
            )
            session.add(
                HttpRequestMetric(
                    method="GET",
                    path="/new",
                    status_code=200,
                    duration_ms=1,
                    created_at=now - datetime.timedelta(days=1),
                )
            )
            session.commit()

        deleted = purge_old_http_request_metrics(retention_days=7, now=now, db_engine=self.engine)

        with Session(self.engine) as session:
            paths = [row.path for row in session.exec(select(HttpRequestMetric)).all()]

        self.assertEqual(deleted, 1)
        self.assertEqual(paths, ["/new"])


if __name__ == "__main__":
    unittest.main()
