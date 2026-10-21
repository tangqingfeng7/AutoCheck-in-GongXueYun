import datetime as dt
import json
import os
import smtplib
import unittest
from email.mime.text import MIMEText
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from server import mail_delivery as mail, task_runner, task_status
from server.attendance_confirmation import confirm_attendance
from server.models import User
from server.settings_store import get_setting, upsert_setting
from server.user_runtime import apply_execution_results_to_user


class AttendanceTest(unittest.TestCase):
    def test_eventual_record_only_retries_reads(self):
        client = Mock()
        client.get_checkin_records.side_effect = [[], [{"type": "START", "createTime": "2026-10-21 08:30:00"}]]
        with patch("server.attendance_confirmation.time.sleep"):
            value = confirm_attendance(client, "2026-10-21", "START")
        self.assertTrue(value["record_confirmed"])
        self.assertEqual(client.get_checkin_records.call_count, 2)
        client.submit_clock_in.assert_not_called()

    def test_wrong_day_or_type_not_success(self):
        client = Mock()
        client.get_checkin_records.return_value = [{"type": "END", "createTime": "2026-10-21 17:30:00"},
                                                 {"type": "START", "createTime": "2026-10-20 08:30:00"}]
        value = confirm_attendance(client, "2026-10-21", "START", attempts=1)
        self.assertFalse(value["record_confirmed"])

    def test_query_timeout_is_unknown_not_missing(self):
        client = Mock()
        client.get_checkin_records.side_effect = TimeoutError()
        value = confirm_attendance(client, "2026-10-21", "START", attempts=1)
        self.assertEqual(value["confirmation_state"], "query_failed")

    def test_pending_is_not_persisted_as_success(self):
        user = SimpleNamespace(userInfo={}, planInfo={}, pushNotifications=[])
        self.assertEqual(apply_execution_results_to_user(user, [{"status": "pending"}], {}), "Pending")

    def test_submit_once_then_pending_when_no_record(self):
        from tests.test_alipay_clockin_verification import build_task_config
        client = Mock()
        client.get_checkin_records.return_value = []
        client.submit_clock_in.return_value = {"status": "success"}
        with patch.object(task_runner, "upload_img", return_value=[]), patch("server.attendance_confirmation.time.sleep"):
            result = task_runner.perform_clock_in(client, build_task_config(), forced_checkin_type="START")
        self.assertEqual(result["status"], "pending")
        client.submit_clock_in.assert_called_once()
        self.assertEqual(client.get_checkin_records.call_count, 4)

    def test_lost_submit_response_is_pending_never_replayed(self):
        from tests.test_alipay_clockin_verification import build_task_config
        client=Mock();client.get_checkin_records.return_value=[]
        client.submit_clock_in.side_effect=ValueError('结果可能已被服务器接收')
        with patch.object(task_runner,'upload_img',return_value=[]):
            result=task_runner.perform_clock_in(client,build_task_config(),forced_checkin_type='START')
        self.assertEqual(result['status'],'pending');client.submit_clock_in.assert_called_once()


class MailTest(unittest.TestCase):
    def setUp(self):
        self.db = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(self.db)
        self.patches = [patch.object(mail, "engine", self.db),
                        patch.dict(os.environ, {"USER_PASSWORD_KEY": "local-fixture-key"})]
        for p in self.patches: p.start()
        self.config = {"username": "sender@example.test", "password": "fixture-secret", "tenant_id": "tenant-a"}
        self.smtp = Mock()
        self.smtp.__enter__ = Mock(return_value=self.smtp)
        self.smtp.__exit__ = Mock(return_value=False)
        self.smtp.send_message.return_value = {}
        self.transport = patch.object(mail.smtplib, "SMTP_SSL", return_value=self.smtp)
        self.transport.start()

    def tearDown(self):
        self.transport.stop()
        for p in reversed(self.patches): p.stop()
        self.db.dispose()

    def message(self):
        m = MIMEText('fixture content', 'plain', 'utf-8')
        m['To'] = 'receiver@example.test'; m['From'] = 'sender@example.test'; m['Subject'] = 'fixture'
        return m

    def row(self):
        with Session(self.db) as s:
            from server.models import SystemSetting
            from sqlmodel import select
            return s.exec(select(SystemSetting)).one()

    def force_due(self):
        with Session(self.db) as s:
            row = self.row()
            value = dict(row.value); value['next_attempt'] = 0
            upsert_setting(s, row.key.split('tenant-a:', 1)[-1], value, 'tenant-a'); s.commit()

    def test_dedup_success_and_tenant_scope(self):
        self.assertEqual(mail.enqueue_and_send(self.config, self.message()), 'sent')
        self.assertEqual(mail.enqueue_and_send(self.config, self.message()), 'sent')
        self.smtp.send_message.assert_called_once()
        with Session(self.db) as s:
            self.assertEqual(mail.mail_status(s, 'tenant-b'), [])
            serialized = json.dumps(mail.mail_status(s, 'tenant-a'))
            self.assertNotIn('fixture-secret', serialized)
            self.assertNotIn('receiver@', serialized)

    def test_transient_connect_retries_persisted_encrypted(self):
        self.transport.stop()
        with patch.object(mail.smtplib, 'SMTP_SSL', side_effect=TimeoutError()):
            self.assertEqual(mail.enqueue_and_send(self.config, self.message()), 'retry')
        row = self.row()
        self.assertTrue(row.value['payload'].startswith('enc$'))
        self.assertNotIn('fixture content', json.dumps(row.value))
        self.force_due()
        with patch.object(mail.smtplib, 'SMTP_SSL', return_value=self.smtp):
            key = row.key.split('tenant-a:', 1)[-1]
            self.assertEqual(mail._send(key, 'tenant-a', self.config), 'sent')
        self.assertEqual(self.row().value['attempts'], 2)

    def test_bad_password_not_retried(self):
        self.smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b'fixture')
        self.assertEqual(mail.enqueue_and_send(self.config, self.message()), 'failed')
        self.smtp.send_message.assert_not_called()

    def test_disconnect_after_data_is_uncertain_and_not_replayed(self):
        self.smtp.send_message.side_effect = smtplib.SMTPServerDisconnected('fixture')
        self.assertEqual(mail.enqueue_and_send(self.config, self.message()), 'uncertain')
        self.assertEqual(mail.enqueue_and_send(self.config, self.message()), 'uncertain')
        self.smtp.send_message.assert_called_once()

    def test_crash_recovery_never_replays_sending(self):
        with Session(self.db) as s:
            upsert_setting(s, 'mail-outbox:crash', {'status': 'sending'}, 'tenant-a'); s.commit()
        self.assertEqual(mail._send('mail-outbox:crash', 'tenant-a', self.config), 'uncertain')
        self.smtp.send_message.assert_not_called()

    def test_retry_exhaustion_is_bounded(self):
        self.transport.stop()
        with patch.object(mail.smtplib, 'SMTP_SSL', side_effect=TimeoutError()):
            mail.enqueue_and_send(self.config, self.message())
            key = self.row().key.split('tenant-a:', 1)[-1]
            for i in range(3):
                self.force_due(); result = mail._send(key, 'tenant-a', self.config)
        self.assertEqual(result, 'failed')
        self.assertEqual(self.row().value['attempts'], 4)

    def test_background_worker_retries_after_restart_using_current_credentials(self):
        self.transport.stop()
        with patch.object(mail.smtplib, 'SMTP_SSL', side_effect=TimeoutError()):
            mail.enqueue_and_send(self.config, self.message())
        self.force_due()
        cfg={**self.config, 'enabled':True}
        with patch.object(mail.smtplib, 'SMTP_SSL', return_value=self.smtp), \
             patch.object(task_runner, '_load_global_smtp_settings', return_value=cfg):
            mail.process_outbox()
        self.assertEqual(self.row().value['status'],'sent')
        self.smtp.send_message.assert_called_once()

    def test_expired_queue_payload_never_sent(self):
        self.transport.stop()
        with patch.object(mail.smtplib, 'SMTP_SSL', side_effect=TimeoutError()):
            mail.enqueue_and_send(self.config, self.message())
        self.force_due()
        with Session(self.db) as s:
            row=self.row(); key=row.key.split('tenant-a:',1)[-1]
            value=dict(row.value); value['expires_at']=0
            upsert_setting(s,key,value,'tenant-a');s.commit()
        self.assertEqual(mail._send(key,'tenant-a',self.config),'expired')
        self.smtp.send_message.assert_not_called()


class MonitorTest(unittest.TestCase):
    def user(self):
        return User(id=1, phone='fixture', password='fixture', enable_clockin=True,
                    clockIn={'mode': 'none', 'schedule': {'weekdays': [1,2,3,4,5],
                             'startTime': '08:30', 'endTime': '17:30', 'startDate': '2026-10-19', 'totalDays': 180}})

    def test_due_grace_and_weekend(self):
        user = self.user()
        with patch.dict(os.environ, {'SCHEDULER_JITTER_SECONDS': '0'}):
            self.assertEqual(task_status.due_targets(user, dt.datetime(2026,10,21,8,34,tzinfo=task_status.TZ)), [])
            self.assertEqual(task_status.due_targets(user, dt.datetime(2026,10,21,8,35,tzinfo=task_status.TZ)), ['START'])
            self.assertEqual(task_status.due_targets(user, dt.datetime(2026,10,24,18,tzinfo=task_status.TZ)), [])

    def test_disabled_and_expired_are_not_missing(self):
        user = self.user(); user.enable_clockin = False
        self.assertEqual(task_status.due_targets(user, dt.datetime(2026,10,21,18,tzinfo=task_status.TZ)), [])
        user.enable_clockin = True
        self.assertEqual(task_status.due_targets(user, dt.datetime(2027,10,21,18,tzinfo=task_status.TZ)), [])

    def test_custom_skip_not_alerted(self):
        user=self.user(); user.clockIn['mode']='custom'; user.clockIn['customDays']=[]
        self.assertEqual(task_status.due_targets(user, dt.datetime(2026,10,21,18,tzinfo=task_status.TZ)), [])

    def test_missing_record_alert_is_read_only_and_throttled(self):
        db=create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(db)
        user=self.user(); user.userInfo={'token':'fixture'}
        client=Mock(); client.get_checkin_records.return_value=[]
        now=dt.datetime(2026,10,21,9,tzinfo=task_status.TZ)
        with patch.object(task_status,'engine',db), patch.dict(os.environ,{'SCHEDULER_JITTER_SECONDS':'0'}), \
             patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), \
             patch.object(task_runner,'_load_global_smtp_settings',return_value={}), \
             patch('server.util.MessagePush.MessagePusher.push') as push:
            task_status.detect_user(user,now)
            task_status.detect_user(user,now)
        client.submit_clock_in.assert_not_called()
        client.login.assert_not_called()
        client.get_checkin_records.assert_called_once()
        self.assertEqual(push.call_count,1)
        self.assertEqual(push.call_args.args[0][0]['details']['检测状态'],'missing')
        db.dispose()

    def test_expired_login_is_unknown_not_missing_and_never_logs_in(self):
        db=create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(db)
        client=Mock()
        with patch.object(task_status,'engine',db), patch.dict(os.environ,{'SCHEDULER_JITTER_SECONDS':'0'}), \
             patch('server.coreApi.MainLogicApi.ApiClient',return_value=client), \
             patch.object(task_runner,'_load_global_smtp_settings',return_value={}), \
             patch('server.util.MessagePush.MessagePusher.push') as push:
            task_status.detect_user(self.user(),dt.datetime(2026,10,21,9,tzinfo=task_status.TZ))
        client.login.assert_not_called();client.get_checkin_records.assert_not_called()
        self.assertEqual(push.call_args.args[0][0]['details']['检测状态'],'login_expired')
        db.dispose()


class ScopeTest(unittest.TestCase):
    def test_task_panel_blocks_cross_tenant_and_requires_login(self):
        from server.main import app
        from server import api
        from server.database import get_session
        from fastapi.testclient import TestClient
        db=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        SQLModel.metadata.create_all(db)
        with Session(db) as s:
            s.add(User(id=11,tenant_id='tenant-a',phone='fixture',password='fixture'));s.commit()
        def session():
            with Session(db) as s: yield s
        original=dict(app.dependency_overrides)
        try:
            app.dependency_overrides[get_session]=session
            app.dependency_overrides[api.require_users_read]=lambda:{'role':'admin','sub':'fixture','tenant_id':'tenant-b'}
            client=TestClient(app, base_url='http://127.0.0.1')
            self.assertEqual(client.get('/api/users/11/task-status').status_code,404)
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(original);db.dispose()


if __name__ == '__main__':
    unittest.main()
