import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from server import api
from server.models import AppUser, AuditLog, BatchJob, BatchJobItem, SystemSetting, User


class GovernanceHardeningTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)

    def test_audit_log_purge_is_disabled_by_default(self):
        with Session(self.engine) as session:
            session.add(AuditLog(actor="admin", action="probe", target_user_id=None, detail={}))
            session.commit()

            with patch.dict("os.environ", {"ALLOW_AUDIT_LOG_PURGE": ""}, clear=False):
                with self.assertRaises(HTTPException) as ctx:
                    api.clear_audit_logs(session=session, admin={"sub": "admin"})

            self.assertEqual(ctx.exception.status_code, 403)
            self.assertEqual(len(session.exec(select(AuditLog)).all()), 1)

    def test_delete_user_soft_deletes_and_keeps_audit_trail(self):
        with Session(self.engine) as session:
            user = User(phone="13800000000", password="encrypted-password")
            session.add(user)
            session.commit()
            session.refresh(user)

            result = api.delete_user(session=session, user_id=user.id, admin={"sub": "admin"})

            deleted = session.get(User, user.id)
            self.assertEqual(result["ok"], True)
            self.assertIsNotNone(deleted)
            self.assertIsNotNone(deleted.deleted_at)
            self.assertFalse(deleted.app_enabled)
            self.assertFalse(deleted.enable_clockin)
            logs = session.exec(select(AuditLog).where(AuditLog.action == "user.soft_delete")).all()
            self.assertEqual(len(logs), 1)

    def test_user_detail_is_tenant_scoped(self):
        with Session(self.engine) as session:
            user = User(phone="13800000000", password="encrypted-password", tenant_id="default")
            session.add(user)
            session.commit()
            session.refresh(user)

            with self.assertRaises(HTTPException) as ctx:
                api.read_user(
                    session=session,
                    user_id=user.id,
                    viewer={"sub": "operator", "role": "operator", "tenant_id": "acme"},
                )

            self.assertEqual(ctx.exception.status_code, 404)

    def test_user_update_is_tenant_scoped(self):
        with Session(self.engine) as session:
            user = User(phone="13800000001", password="encrypted-password", tenant_id="default")
            session.add(user)
            session.commit()
            session.refresh(user)

            with self.assertRaises(HTTPException) as ctx:
                api.update_user(
                    session=session,
                    user_id=user.id,
                    user_update=api.UserUpdate(remark="cross-tenant-write"),
                    operator={"sub": "operator", "role": "operator", "tenant_id": "acme"},
                )

            self.assertEqual(ctx.exception.status_code, 404)
            self.assertNotEqual(session.get(User, user.id).remark, "cross-tenant-write")

    def test_app_registration_can_be_disabled_by_policy(self):
        from server import api

        request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
        response = SimpleNamespace(headers={}, set_cookie=lambda *args, **kwargs: None)
        req = api.AppRegisterRequest(phone="13800000000", password="strong-pass")

        with patch.dict("os.environ", {"APP_REGISTRATION_ENABLED": "false"}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                api.app_register(request=request, response=response, req=req)

        self.assertEqual(ctx.exception.status_code, 403)

    def test_short_app_password_is_rejected(self):
        from server import api

        request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
        response = SimpleNamespace(headers={}, set_cookie=lambda *args, **kwargs: None)
        req = api.AppRegisterRequest(phone="13800000001", password="short")

        with patch.dict("os.environ", {"APP_REGISTRATION_ENABLED": "true"}, clear=False):
            with self.assertRaises(HTTPException) as ctx:
                api.app_register(request=request, response=response, req=req)

        self.assertEqual(ctx.exception.status_code, 400)

    def test_ai_settings_are_global_and_api_key_is_not_echoed(self):
        from server import api

        with patch.dict("os.environ", {"USER_PASSWORD_KEY": "test-user-password-key"}, clear=False), Session(self.engine) as session:
            saved = api.update_ai_settings(
                session=session,
                admin={"sub": "admin", "role": "admin", "tenant_id": "default"},
                req=api.AiSettingsUpdateRequest(
                    ai={
                        "apiUrl": "https://api.example.com/v1",
                        "apikey": "secret-key",
                        "model": "global-model",
                    }
                ),
            )
            session.commit()

            loaded = api.get_ai_settings(
                session=session,
                admin={"sub": "admin", "role": "admin", "tenant_id": "default"},
            )
            row = session.get(SystemSetting, "ai")

        self.assertEqual(saved["ai"]["apiUrl"], "https://api.example.com/v1")
        self.assertEqual(saved["ai"]["model"], "global-model")
        self.assertEqual(saved["ai"]["apikey"], "")
        self.assertTrue(saved["ai"]["hasApiKey"])
        self.assertEqual(loaded["ai"]["apikey"], "")
        self.assertTrue(loaded["ai"]["hasApiKey"])
        self.assertNotIn("secret-key", str(row.value))

    def test_ai_settings_test_keeps_existing_api_key_when_payload_is_blank(self):
        from server import api

        request = SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1"))
        with patch.dict("os.environ", {"USER_PASSWORD_KEY": "test-user-password-key"}, clear=False), Session(self.engine) as session:
            api.update_ai_settings(
                session=session,
                admin={"sub": "admin", "role": "admin", "tenant_id": "default"},
                req=api.AiSettingsUpdateRequest(
                    ai={
                        "apiUrl": "https://api.example.com/v1",
                        "apikey": "secret-key",
                        "model": "global-model",
                    }
                ),
            )

            with patch.object(api, "_run_ai_connectivity_test", return_value={"ok": True}) as runner:
                result = api.test_ai_settings(
                    request=request,
                    session=session,
                    admin={"sub": "admin", "role": "admin", "tenant_id": "default"},
                    req=api.AiSettingsTestRequest(
                        ai={
                            "apiUrl": "https://api.example.com/v2",
                            "apikey": "",
                            "model": "new-model",
                        }
                    ),
                )

        tested_settings = runner.call_args.args[1]
        self.assertEqual(result, {"ok": True})
        self.assertEqual(tested_settings["apiUrl"], "https://api.example.com/v2")
        self.assertEqual(tested_settings["apikey"], "secret-key")
        self.assertEqual(tested_settings["model"], "new-model")

    def test_report_generation_uses_global_ai_settings_not_user_settings(self):
        from server import api

        with patch("server.api.engine", self.engine):
            with Session(self.engine) as session:
                api.update_ai_settings(
                    session=session,
                    admin={"sub": "admin", "role": "admin", "tenant_id": "default"},
                    req=api.AiSettingsUpdateRequest(
                        ai={
                            "apiUrl": "https://api.example.com/v1",
                            "apikey": "secret-key",
                            "model": "global-model",
                        }
                    ),
                )
                user = User(
                    phone="13800000000",
                    password="encrypted-password",
                    enable_clockin=False,
                    ai={},
                    planInfo={"planPaper": {"dayPaperNum": 300}},
                    userInfo={"userId": "u-1"},
                )
                session.add(user)
                session.commit()
                session.refresh(user)

                fake_client = SimpleNamespace(
                    get_submitted_reports_info=lambda report_type: {"flag": 0, "data": []},
                    get_job_info=lambda: {"practiceCompanyEntity": {}},
                )
                with (
                    patch.object(api, "ApiClient", return_value=fake_client),
                    patch.object(api, "_ensure_remote_runtime"),
                    patch.object(api, "check_ai_generation_quota"),
                    patch.object(api, "generate_article", return_value="generated") as generated,
                ):
                    result = api._generate_report_content_for_user(user, "daily", None, generate_content=True)

        used_config = generated.call_args.args[0]
        self.assertEqual(result["content"], "generated")
        self.assertEqual(used_config.get_value("config.ai.model"), "global-model")
        self.assertEqual(used_config.get_value("config.ai.apiUrl"), "https://api.example.com/v1")
        self.assertEqual(used_config.get_value("config.ai.apikey"), "secret-key")

    def test_report_generation_ignores_legacy_user_ai_without_global_settings(self):
        from server import api

        user = User(
            id=42,
            tenant_id="default",
            phone="13800000000",
            password="encrypted-password",
            enable_clockin=False,
            ai={
                "apiUrl": "https://api.example.com/v1",
                "apikey": "legacy-key",
                "model": "legacy-model",
            },
            planInfo={"planPaper": {"dayPaperNum": 300}},
            userInfo={"userId": "u-1"},
        )
        with (
            patch("server.api.engine", self.engine),
            patch.object(api, "ApiClient"),
            patch.object(api, "generate_article") as generated,
            self.assertRaises(HTTPException) as ctx,
        ):
            api._generate_report_content_for_user(user, "daily", None, generate_content=True)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("AI 设置", str(ctx.exception.detail))
        generated.assert_not_called()

    def test_app_user_can_update_own_push_notifications(self):
        from server import api

        with Session(self.engine) as session:
            user = User(tenant_id="default", phone="13800000000", password="encrypted-password")
            session.add(user)
            session.commit()
            session.refresh(user)
            app_user = AppUser(
                tenant_id="default",
                phone="13800000000",
                password_hash="hash",
                enabled=True,
                bound_user_id=user.id,
            )
            session.add(app_user)
            session.commit()
            session.refresh(app_user)

            updated = api.app_update_me(
                session=session,
                payload={"sub": f"app:{app_user.id}", "role": "user", "tenant_id": "default"},
                req=api.AppMeUpdateRequest(
                    pushNotifications=[
                        {"type": "Server", "enabled": True, "sendKey": "server-key"},
                        {"type": "SMTP", "enabled": True, "to": "demo@qq.com"},
                    ]
                ),
            )
            saved = session.get(User, user.id)

        self.assertEqual(
            updated["pushNotifications"],
            [
                {"type": "Server", "enabled": True, "sendKey": "server-key"},
                {"type": "SMTP", "enabled": True, "to": "demo@qq.com"},
            ],
        )
        self.assertEqual(saved.pushNotifications, updated["pushNotifications"])

    def test_batch_run_rejects_duplicate_and_oversized_requests(self):
        from server import api

        with Session(self.engine) as session:
            session.add(User(tenant_id="default", phone="13800000010", password="encrypted"))
            session.add(User(tenant_id="default", phone="13800000011", password="encrypted"))
            session.commit()

            with patch.dict("os.environ", {"BATCH_JOB_MAX_USERS": "1"}, clear=False):
                with patch("server.api.engine", self.engine):
                    with self.assertRaises(HTTPException) as ctx:
                        api.run_users_batch(
                            request=SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1")),
                            req=api.BatchRunRequest(ids=[1, 1], concurrency=1),
                            operator={"sub": "operator", "role": "operator", "tenant_id": "default"},
                        )

        self.assertEqual(ctx.exception.status_code, 400)

    def test_batch_run_replays_same_idempotency_key_without_duplicate_job(self):
        from server import api

        with Session(self.engine) as session:
            users = [
                User(tenant_id="default", phone="13800000020", password="encrypted"),
                User(tenant_id="default", phone="13800000021", password="encrypted"),
            ]
            session.add_all(users)
            session.commit()
            for user in users:
                session.refresh(user)

        request = SimpleNamespace(headers={"Idempotency-Key": "batch-run-20260529"}, client=SimpleNamespace(host="127.0.0.1"))
        operator = {"sub": "operator", "role": "operator", "tenant_id": "default"}
        req = api.BatchRunRequest(ids=[users[0].id, users[1].id], concurrency=2)

        with patch("server.api.engine", self.engine):
            first = api.run_users_batch(request=request, req=req, operator=operator)
            second = api.run_users_batch(request=request, req=req, operator=operator)
            with self.assertRaises(HTTPException) as conflict:
                api.run_users_batch(
                    request=request,
                    req=api.BatchRunRequest(ids=[users[0].id], concurrency=1),
                    operator=operator,
                )

        with Session(self.engine) as session:
            jobs = session.exec(select(BatchJob)).all()

        self.assertEqual(first, second)
        self.assertEqual(first["queued"], 2)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(conflict.exception.status_code, 409)

    def test_manual_run_replays_same_idempotency_key_without_duplicate_task(self):
        from server import api

        with Session(self.engine) as session:
            user = User(tenant_id="default", phone="13800000040", password="encrypted")
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        request = SimpleNamespace(
            headers={"Idempotency-Key": "manual-run-20260529"},
            client=SimpleNamespace(host="127.0.0.1"),
        )
        operator = {"sub": "operator", "role": "operator", "tenant_id": "default"}
        req = api.AppRunRequest(task_type="weekly_report", force_report=True, target_period="2026-05-22")

        with patch("server.api.engine", self.engine):
            with (
                patch.object(api, "user_to_config", return_value={"config": {}}),
                patch.object(api, "run_task_by_config", return_value=[{"status": "success", "task_type": "周报提交"}]) as runner,
                patch.object(api, "apply_execution_results_to_user", return_value="Success"),
            ):
                with Session(self.engine) as session:
                    first = api.run_user_task(
                        request=request,
                        session=session,
                        user_id=user_id,
                        req=req,
                        operator=operator,
                    )
                with Session(self.engine) as session:
                    second = api.run_user_task(
                        request=request,
                        session=session,
                        user_id=user_id,
                        req=req,
                        operator=operator,
                    )

        self.assertEqual(first, second)
        self.assertEqual(first["results"][0]["task_type"], "周报提交")
        runner.assert_called_once()

    def test_retry_failed_batch_items_requeues_failed_rows(self):
        from server import api

        with Session(self.engine) as session:
            users = [
                User(tenant_id="default", phone="13800000030", password="encrypted"),
                User(tenant_id="default", phone="13800000031", password="encrypted"),
            ]
            session.add_all(users)
            session.commit()
            for user in users:
                session.refresh(user)
            job = BatchJob(
                tenant_id="default",
                created_by="operator",
                status="done",
                total=2,
                completed=2,
                success=1,
                fail=1,
                user_ids=[u.id for u in users],
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            failed_item = BatchJobItem(
                tenant_id="default",
                job_id=job.id,
                user_id=users[1].id,
                status="fail",
                attempts=3,
                max_attempts=3,
                error="worker timeout",
            )
            success_item = BatchJobItem(
                tenant_id="default",
                job_id=job.id,
                user_id=users[0].id,
                status="success",
                attempts=1,
                max_attempts=3,
            )
            session.add_all([failed_item, success_item])
            session.commit()
            session.refresh(job)
            session.refresh(failed_item)
            failed_item_id = failed_item.id
            job_id = job.id

        with patch("server.api.engine", self.engine):
            with Session(self.engine) as session:
                before_retry = api.read_batch_job(
                    session=session,
                    job_id=job_id,
                    viewer={"sub": "operator", "role": "operator", "tenant_id": "default"},
                )
                self.assertEqual(before_retry["failed"], 1)
                result = api.retry_failed_batch_job_items(
                    session=session,
                    job_id=job_id,
                    operator={"sub": "operator", "role": "operator", "tenant_id": "default"},
                )

        with Session(self.engine) as session:
            job = session.get(BatchJob, job_id)
            failed_item = session.get(BatchJobItem, failed_item_id)

        self.assertEqual(result["ok"], True)
        self.assertEqual(result["requeued"], 1)
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.completed, 1)
        self.assertEqual(job.fail, 0)
        self.assertIsNone(job.finished_at)
        self.assertEqual(failed_item.status, "queued")
        self.assertEqual(failed_item.attempts, 0)
        self.assertIsNone(failed_item.error)
        self.assertIsNone(failed_item.started_at)
        self.assertIsNone(failed_item.finished_at)

    def test_ai_audit_detail_includes_prompt_version(self):
        from server.api import _ai_audit_detail

        config = SimpleNamespace(
            get_value=lambda key: {
                "config.ai": {
                    "apikey": "key",
                    "apiUrl": "https://api.example.com",
                    "model": "gpt-test",
                },
            }.get(key)
        )

        detail = _ai_audit_detail(config, "daily report")

        self.assertEqual(detail["prompt_version"], "2026-05-29.1")
        self.assertEqual(detail["model"], "gpt-test")

    def test_ai_generation_quota_uses_tenant_and_user_buckets(self):
        from server.ai_governance import check_ai_generation_quota

        with patch.dict(
            "os.environ",
            {
                "AI_TENANT_DAILY_LIMIT": "10",
                "AI_USER_DAILY_LIMIT": "3",
                "AI_RATE_LIMIT_WINDOW_SECONDS": "86400",
            },
            clear=False,
        ):
            with patch("server.ai_governance.check_rate_limit") as check_rate_limit:
                check_ai_generation_quota(tenant_id="acme", user_id=42)

        self.assertEqual(check_rate_limit.call_count, 2)
        self.assertEqual(check_rate_limit.call_args_list[0].args[:3], ("ai:tenant:acme", 10, 86400))
        self.assertEqual(check_rate_limit.call_args_list[1].args[:3], ("ai:user:acme:42", 3, 86400))

    def test_report_generation_quota_fails_before_remote_runtime_calls(self):
        from server import api

        user = User(tenant_id="acme", phone="13800000099", password="encrypted")
        api_client = SimpleNamespace(
            get_submitted_reports_info=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not refetch submitted reports")),
            get_job_info=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not fetch job info")),
        )
        config_data = {
            "config": {
                "ai": {
                    "apikey": "key",
                    "apiUrl": "https://api.example.com",
                    "model": "model",
                }
            }
        }

        with (
            patch.object(api, "user_to_config", return_value=config_data),
            patch.object(api, "ApiClient", return_value=api_client),
            patch.object(api, "_ensure_remote_runtime") as ensure_runtime,
            patch.object(api, "check_ai_generation_quota", side_effect=HTTPException(status_code=429, detail="quota")),
            patch.object(api, "generate_article") as generate_article,
        ):
            with self.assertRaises(HTTPException) as ctx:
                api._generate_report_content_for_user(user, "daily", "2026-05-22")

        self.assertEqual(ctx.exception.status_code, 429)
        ensure_runtime.assert_not_called()
        generate_article.assert_not_called()

    def test_legacy_daily_generate_endpoint_uses_shared_report_helper(self):
        from server import api

        with Session(self.engine) as session:
            user = User(tenant_id="default", phone="13800000098", password="encrypted")
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

            generated = {
                "config_data": {"runtime": "updated"},
                "title": "第1天日报",
                "content": "daily content",
                "api_client": SimpleNamespace(),
                "config": SimpleNamespace(),
                "meta": api._get_report_meta("daily"),
                "submitted": {"data": []},
                "job_info": {},
            }
            with (
                patch.object(api, "_generate_report_content_for_user", return_value=generated) as generate,
                patch.object(api, "sync_runtime_fields_to_user"),
                patch.object(api, "_ai_audit_detail", return_value={"prompt_version": "test"}),
            ):
                result = api.generate_daily_report(
                    request=SimpleNamespace(headers={}, client=SimpleNamespace(host="127.0.0.1")),
                    session=session,
                    user_id=user_id,
                    operator={"sub": "operator", "role": "operator", "tenant_id": "default"},
                )

        self.assertEqual(result["content"], "daily content")
        self.assertEqual(result["title"], "第1天日报")
        self.assertEqual(generate.call_args.args[1:], ("daily", None))


if __name__ == "__main__":
    unittest.main()
